import { z } from "zod";
import { database, readQueries } from "../../../lib/db";
import { changePassword, loginPassword, registerPassword, rateLimit, sendCode, session, verifyCode } from "../../../lib/auth";
import { decrypt, equals, hash, origin, PublicError, required } from "../../../lib/security";
import { activateLicense, activationSchema, adminLicense, manualLicense } from "../../../lib/licenses";
import { createOrder, receiveWebhook, reconcileOrder } from "../../../lib/payments";
import { claimTrial } from "../../../lib/trials";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const emailSchema = z.string().trim().toLowerCase().pipe(z.email().max(254));
const phoneSchema = z.string().max(20).regex(/^[+\d\s-]*$/);
const passwordSchema = z.string().min(12).max(128);

async function body(request: Request, max = 16384) {
  if (!request.headers.get("content-type")?.startsWith("application/json")) throw new PublicError("json_required", 415);
  const reader = request.body?.getReader();
  if (!reader) throw new PublicError("invalid_body");
  const chunks: Uint8Array[] = []; let size = 0;
  try {
    while (true) {
      const chunk = await reader.read(); if (chunk.done) break;
      size += chunk.value.length;
      if (size > max) { await reader.cancel(); throw new PublicError("body_too_large", 413); }
      chunks.push(chunk.value);
    }
    return JSON.parse(Buffer.concat(chunks).toString());
  } catch (error) { if (error instanceof PublicError) throw error; throw new PublicError("invalid_json"); }
}
const json = (data: unknown, status = 200, headers = {}) => Response.json(data, { status, headers: { "Cache-Control": "no-store", ...headers } });

async function handle(request: Request) {
  const path = new URL(request.url).pathname.slice(5);
  try {
    if (path === "cron/cleanup" && request.method === "GET") {
      if (!equals(request.headers.get("authorization") ?? "", `Bearer ${required("CRON_SECRET")}`)) throw new PublicError("forbidden", 403);
      await database().query("DELETE FROM sessions WHERE expires_at<now()");
      await database().query("DELETE FROM email_codes WHERE expires_at<now()");
      await database().query("DELETE FROM license_nonces WHERE expires_at<now()");
      await database().query("DELETE FROM rate_limits WHERE resets_at<now()-interval '1 day'");
      return json({ success: true });
    }
    const machine = path === "licenses/activate" || path === "payos/webhook";
    if (request.method !== "GET" && !machine && request.headers.get("origin") !== origin()) throw new PublicError("invalid_origin", 403);
    const ip = process.env.VERCEL ? request.headers.get("x-vercel-forwarded-for")?.split(",")[0] ?? "unknown" : "local";
    if (path !== "payos/webhook") await rateLimit(`ip:${ip}:${path}`, 120, 60);
    if (request.method === "POST") {
      const payload = await body(request, path === "payos/webhook" ? 65536 : 16384);
      if (path === "auth/register" || path === "auth/login") {
        const data=z.object({email:emailSchema,password:passwordSchema,phone:phoneSchema.optional()}).parse(payload);
        await rateLimit(`password-ip:${ip}`,30,600);
        if (path==="auth/register") await rateLimit(`signup-ip:${ip}`,5,86400);
        const token=path==="auth/register"?await registerPassword(data.email,data.password,data.phone):await loginPassword(data.email,data.password);
        return json({success:true},200,{"Set-Cookie":`rd_session=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800${origin().startsWith("https:")?"; Secure":""}`});
      }
      if (path === "payos/webhook") { await receiveWebhook(payload); return json({ success: true }); }
      if (path === "licenses/activate") {
        const parsed = activationSchema.parse(payload);
        await rateLimit(`license:${hash(parsed.key)}`, 60, 3600);
        return json({ success: true, lease: await activateLicense(parsed) });
      }
      if (path === "auth/code") {
        const { email } = z.object({ email: emailSchema }).parse(payload);
        await rateLimit(`send-ip:${ip}`, 12, 3600);
        await sendCode(email); return json({ success: true });
      }
      if (path === "auth/verify") {
        const { email, code } = z.object({ email: emailSchema, code: z.string().regex(/^\d{6}$/) }).parse(payload);
        const token = await verifyCode(email, code);
        return json({ success: true }, 200, { "Set-Cookie": `rd_session=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800${origin().startsWith("https:") ? "; Secure" : ""}` });
      }
      const user = await session(request, path.startsWith("admin/"));
      if (path === "auth/password") {
        const data=z.object({current_password:passwordSchema,new_password:passwordSchema,confirm_password:passwordSchema}).parse(payload);
        if (data.new_password!==data.confirm_password) throw new PublicError("password_mismatch");
        await rateLimit(`password-change-ip:${ip}`,20,900);
        const currentToken=request.headers.get("cookie")?.split(";").map(value=>value.trim()).find(value=>value.startsWith("rd_session="))?.slice(11)??"";
        const token=await changePassword(user.id,data.current_password,data.new_password,hash(currentToken));
        return json({success:true},200,{"Set-Cookie":`rd_session=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800${origin().startsWith("https:")?"; Secure":""}`});
      }
      if (path === "auth/logout") {
        const token = request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith("rd_session="))?.slice(11) ?? "";
        await database().query("DELETE FROM sessions WHERE digest=$1", [hash(token)]);
        return json({ success: true }, 200, { "Set-Cookie": "rd_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" });
      }
      if (path === "licenses/trial") {
        await rateLimit(`trial:${user.id}`,10,3600);
        return json({success:true,license_id:await claimTrial(user.id)});
      } else if (path === "profile") {
        const { phone } = z.object({ phone: z.string().max(20).regex(/^[+\d\s-]*$/) }).parse(payload);
        await database().query("UPDATE users SET phone=$1 WHERE id=$2", [phone || null, user.id]);
      } else if (path === "orders") {
        const data = z.object({ plan_id: z.string().max(50), request_id: z.uuid() }).parse(payload);
        await rateLimit(`orders:${user.id}`, 20, 3600);
        return json({ success: true, order: await createOrder(user.id, data.plan_id, data.request_id) });
      } else if (path === "orders/reconcile") {
        const data = z.object({ order_id: z.uuid() }).parse(payload);
        await rateLimit(`reconcile:${user.id}`, 30, 3600);
        await reconcileOrder(user.id, data.order_id);
      } else if (path === "admin/license") {
        const data = z.object({ id: z.uuid(), action: z.enum(["lock","unlock","revoke","reset","extend"]), days: z.number().int().min(1).max(36500).optional() }).parse(payload);
        await adminLicense(user.id, data.id, data.action, data.days);
      } else if (path === "admin/manual") {
        const data = z.object({ email: emailSchema, plan_id: z.string().max(50), request_id: z.uuid() }).parse(payload);
        await manualLicense(user.id, data.email, data.plan_id, data.request_id);
      } else throw new PublicError("not_found", 404);
      return json({ success: true });
    }
    if (path === "plans") return json({ plans: (await database().query("SELECT id,name,amount,duration_days FROM plans WHERE active=true ORDER BY amount")).rows });
    const user = await session(request, path.startsWith("admin/"));
    if (path === "dashboard") {
      const page = Math.floor(Math.max(0, Math.min(1000000, Number(new URL(request.url).searchParams.get("page")) || 0)));
      const [orderResult,licenseResult,summaryResult]=await readQueries([
        {sql:"SELECT id,order_code,plan_id,amount,status,checkout_url,created_at,paid_at FROM orders WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50 OFFSET $2",params:[user.id,page*50]},
        {sql:"SELECT id,plan_id,key_cipher,status,expires_at,installation_key,created_at FROM licenses WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50 OFFSET $2",params:[user.id,page*50]},
        {sql:"SELECT (SELECT count(*) FROM orders WHERE user_id=$1) AS orders,(SELECT count(*) FROM licenses WHERE user_id=$1) AS licenses,EXISTS(SELECT 1 FROM administrator_accounts WHERE user_id=$1) AS admin,EXISTS(SELECT 1 FROM trial_claims WHERE user_id=$1) AS trial_claimed,EXISTS(SELECT 1 FROM orders WHERE user_id=$1 AND status='pending') AS has_pending_orders",params:[user.id]},
      ]);
      const totals=summaryResult.rows[0];
      return json({ user: { ...user, admin: !!totals.admin }, trial_claimed:!!totals.trial_claimed,has_pending_orders:!!totals.has_pending_orders, orders:orderResult.rows, page, has_more: Math.max(Number(totals.orders),Number(totals.licenses))>(page+1)*50, licenses: licenseResult.rows.map(({key_cipher,installation_key,...rest}) => ({...rest,key:decrypt(key_cipher),bound:!!installation_key})) });
    }
    if (path === "admin/overview") {
      const page = Math.max(0, Math.min(1000000, Number(new URL(request.url).searchParams.get("page")) || 0));
      const offset = Math.floor(page)*50;
      const [users,orders,licenses,revenue,totals,audit]=await readQueries([
        {sql:"SELECT id,email,phone,created_at FROM users ORDER BY created_at DESC LIMIT 50 OFFSET $1",params:[offset]},
        {sql:"SELECT orders.*,users.email FROM orders JOIN users ON users.id=orders.user_id ORDER BY orders.created_at DESC LIMIT 50 OFFSET $1",params:[offset]},
        {sql:"SELECT licenses.id,users.email,licenses.status,licenses.expires_at,licenses.plan_id,licenses.installation_key IS NOT NULL AS bound FROM licenses JOIN users ON users.id=licenses.user_id ORDER BY licenses.created_at DESC LIMIT 50 OFFSET $1",params:[offset]},
        {sql:"SELECT coalesce(sum(amount),0) AS revenue,count(*) AS paid_orders FROM orders WHERE status='paid'"},
        {sql:"SELECT (SELECT count(*) FROM users) AS users,(SELECT count(*) FROM orders) AS orders,(SELECT count(*) FROM licenses) AS licenses"},
        {sql:"SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 50 OFFSET $1",params:[offset]},
      ]);
      return json({ users:users.rows,orders:orders.rows,licenses:licenses.rows,revenue:revenue.rows[0],totals:totals.rows[0],audit:audit.rows,page });
    }
    throw new PublicError("not_found", 404);
  } catch (error) {
    if (error instanceof z.ZodError) return json({ error: "invalid_input" }, 400);
    if (error instanceof PublicError) return json({ error: error.code }, error.status);
    return json({ error: "service_unavailable" }, 503);
  }
}
export const GET = handle;
export const POST = handle;
