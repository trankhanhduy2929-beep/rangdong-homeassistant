import { randomBytes, randomInt, randomUUID } from "node:crypto";
import { database, transaction } from "./db";
import { digestCode, equals, hash, PublicError, required } from "./security";
import { batch, clearGuard, d1Enabled, guard, afterSQL } from "./d1-client";
import { verifyCodeD1 } from "./d1-operations";
import { passwordHash, passwordMatches } from "./passwords";

export async function rateLimit(key: string, limit: number, seconds: number) {
  const result = await database().query(
    `INSERT INTO rate_limits(key,count,resets_at) VALUES ($1,1,now()+$2*interval '1 second')
     ON CONFLICT(key) DO UPDATE SET count=CASE WHEN rate_limits.resets_at<now() THEN 1 ELSE rate_limits.count+1 END,
       resets_at=CASE WHEN rate_limits.resets_at<now() THEN now()+$2*interval '1 second' ELSE rate_limits.resets_at END RETURNING count`,
    [hash(key), seconds]);
  if (result.rows[0].count > limit) throw new PublicError("rate_limited", 429);
}
export function isAdmin(email: string) {
  return (process.env.ADMIN_EMAILS ?? "").split(",").map(value => value.trim().toLowerCase()).includes(email);
}
export async function hasAdminRole(userId: string) {
  return !!(await database().query("SELECT user_id FROM administrator_accounts WHERE user_id=$1",[userId])).rows[0];
}
export async function session(request: Request, admin = false) {
  const token = request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith("rd_session="))?.slice(11);
  if (!token || token.length > 128) throw new PublicError("login_required", 401);
  const result = await database().query(
    `SELECT users.id,users.email,users.phone FROM sessions JOIN users ON users.id=sessions.user_id WHERE digest=$1 AND expires_at>now()`, [hash(token)]);
  const user = result.rows[0];
  if (!user) throw new PublicError("login_required", 401);
  if (admin && !await hasAdminRole(user.id)) throw new PublicError("forbidden", 403);
  return user as { id: string; email: string; phone: string | null };
}
export async function sendCode(email: string) {
  await rateLimit(`email-send:${email}`, 4, 3600);
  const code = String(randomInt(100000, 1000000));
  await database().query(`INSERT INTO email_codes VALUES($1,$2,now()+interval '10 minutes')
    ON CONFLICT(email) DO UPDATE SET digest=$2,expires_at=now()+interval '10 minutes'`, [email, digestCode(email, code)]);
  const response = await fetch("https://api.resend.com/emails", { method: "POST", signal: AbortSignal.timeout(15000),
    headers: { Authorization: `Bearer ${required("RESEND_API_KEY")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: required("EMAIL_FROM"), to: email, subject: "Mã đăng nhập Rạng Đông",
      text: `Mã xác minh của bạn: ${code}. Hết hạn sau 10 phút. Không chia sẻ mã này.` }) });
  if (!response.ok) throw new PublicError("email_unavailable", 503);
}
export async function verifyCode(email: string, code: string) {
  await rateLimit(`email-verify:${email}`, 8, 600);
  if (d1Enabled()) return verifyCodeD1(email, code, isAdmin(email));
  return transaction(async client => {
    const result = await client.query("SELECT * FROM email_codes WHERE email=$1 AND expires_at>now() FOR UPDATE", [email]);
    if (!result.rows[0] || !equals(result.rows[0].digest, digestCode(email, code))) throw new PublicError("invalid_code", 401);
    await client.query("DELETE FROM email_codes WHERE email=$1", [email]);
    const user = await client.query(`INSERT INTO users(id,email) VALUES($1,$2) ON CONFLICT(email) DO UPDATE SET email=EXCLUDED.email RETURNING id`, [randomUUID(), email]);
    if (isAdmin(email)) await client.query("INSERT INTO administrator_accounts(user_id) VALUES($1) ON CONFLICT DO NOTHING",[user.rows[0].id]);
    const token = randomBytes(32).toString("base64url");
    await client.query("INSERT INTO sessions VALUES($1,$2,now()+interval '7 days')", [hash(token), user.rows[0].id]);
    return token;
  });
}

export async function registerPassword(email: string, password: string, phone?: string) {
  await rateLimit(`register-email:${email}`,5,3600);
  if (isAdmin(email) || (await database().query("SELECT id FROM users WHERE email=$1",[email])).rows[0]) throw new PublicError("account_unavailable",409);
  const encoded=await passwordHash(password), userId=randomUUID(), token=randomBytes(32).toString("base64url");
  if (d1Enabled()) {
    await batch([
      {sql:"INSERT INTO users(id,email,phone) VALUES(?,?,?)",params:[userId,email,phone||null]},
      {sql:"INSERT INTO auth_credentials(user_id,password_hash) VALUES(?,?)",params:[userId,encoded]},
      {sql:`INSERT INTO sessions VALUES(?,?,${afterSQL("'+7 days'")})`,params:[hash(token),userId]},
    ]);
  } else await transaction(async client=>{
    await client.query("INSERT INTO users(id,email,phone) VALUES($1,$2,$3)",[userId,email,phone||null]);
    await client.query("INSERT INTO auth_credentials(user_id,password_hash) VALUES($1,$2)",[userId,encoded]);
    await client.query("INSERT INTO sessions VALUES($1,$2,now()+interval '7 days')",[hash(token),userId]);
  });
  return token;
}
export async function loginPassword(email: string, password: string) {
  await rateLimit(`password-login:${email}`,10,600);
  const record=(await database().query("SELECT users.id,auth_credentials.password_hash FROM users JOIN auth_credentials ON users.id=auth_credentials.user_id WHERE users.email=$1",[email])).rows[0];
  if (!await passwordMatches(password,record?.password_hash)) throw new PublicError("invalid_credentials",401);
  const token=randomBytes(32).toString("base64url");
  if (d1Enabled()) await batch([
    guard("EXISTS(SELECT 1 FROM auth_credentials WHERE user_id=? AND password_hash=?)",[record.id,record.password_hash]),
    {sql:`INSERT INTO sessions VALUES(?,?,${afterSQL("'+7 days'")})`,params:[hash(token),record.id]},clearGuard,
  ]);
  else await transaction(async client=>{
    const current=(await client.query("SELECT password_hash FROM auth_credentials WHERE user_id=$1 FOR UPDATE",[record.id])).rows[0];
    if (current?.password_hash!==record.password_hash) throw new PublicError("invalid_credentials",401);
    await client.query("INSERT INTO sessions VALUES($1,$2,now()+interval '7 days')",[hash(token),record.id]);
  });
  return token;
}

export async function changePassword(userId: string, currentPassword: string, newPassword: string, sessionDigest: string) {
  await rateLimit(`password-change:${userId}`,5,900);
  const record=(await database().query("SELECT password_hash FROM auth_credentials WHERE user_id=$1",[userId])).rows[0];
  if (!await passwordMatches(currentPassword,record?.password_hash)) throw new PublicError("incorrect_current_password",400);
  if (currentPassword===newPassword) throw new PublicError("password_unchanged",400);
  const encoded=await passwordHash(newPassword), token=randomBytes(32).toString("base64url");
  if (d1Enabled()) await batch([
    guard("EXISTS(SELECT 1 FROM auth_credentials WHERE user_id=? AND password_hash=?)",[userId,record.password_hash]),
    guard(`EXISTS(SELECT 1 FROM sessions WHERE digest=? AND user_id=? AND expires_at>${afterSQL("'+0 seconds'")})`,[sessionDigest,userId]),
    {sql:"UPDATE auth_credentials SET password_hash=? WHERE user_id=?",params:[encoded,userId]},
    {sql:"DELETE FROM sessions WHERE user_id=?",params:[userId]},
    {sql:`INSERT INTO sessions VALUES(?,?,${afterSQL("'+7 days'")})`,params:[hash(token),userId]},
    {sql:"INSERT INTO audit_log(id,actor_id,action,target_id) VALUES(?,?,'account.password_changed',?)",params:[randomUUID(),userId,userId]},clearGuard,
  ]);
  else await transaction(async client=>{
    const current=(await client.query("SELECT password_hash FROM auth_credentials WHERE user_id=$1 FOR UPDATE",[userId])).rows[0];
    if (current?.password_hash!==record.password_hash) throw new PublicError("transaction_conflict",409);
    const active=(await client.query("SELECT digest FROM sessions WHERE digest=$1 AND user_id=$2 AND expires_at>now() FOR UPDATE",[sessionDigest,userId])).rows[0];
    if (!active) throw new PublicError("login_required",401);
    await client.query("UPDATE auth_credentials SET password_hash=$1 WHERE user_id=$2",[encoded,userId]);
    await client.query("DELETE FROM sessions WHERE user_id=$1",[userId]);
    await client.query("INSERT INTO sessions VALUES($1,$2,now()+interval '7 days')",[hash(token),userId]);
    await client.query("INSERT INTO audit_log(id,actor_id,action,target_id) VALUES($1,$2,'account.password_changed',$2)",[randomUUID(),userId]);
  });
  return token;
}
