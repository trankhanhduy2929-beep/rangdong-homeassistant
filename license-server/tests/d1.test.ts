import assert from "node:assert/strict";
import { test, mock } from "node:test";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { createHmac, generateKeyPairSync, randomBytes, randomUUID, sign } from "node:crypto";
import { createOrderD1, settlePaymentD1, adminLicenseD1, manualLicenseD1 } from "../lib/d1-operations";
import { d1Database, batch, guard, clearGuard, translate } from "../lib/d1-client";
import { activateLicense, requestMessage } from "../lib/licenses";
import { decrypt, hash } from "../lib/security";
import { POST, GET } from "../app/api/[...path]/route";
import { claimTrial } from "../lib/trials";
import { manualLicense } from "../lib/licenses";
import { changePassword } from "../lib/auth";

const worker = (await import("../cloudflare/" + "worker.js")).default;
process.env.DATABASE_PROVIDER="d1";
process.env.D1_GATEWAY_URL="https://gateway.example.invalid/batch";
process.env.D1_GATEWAY_SECRET=randomBytes(32).toString("hex");
process.env.APP_URL="https://license.example.invalid";
process.env.AUTH_SECRET=randomBytes(48).toString("hex");
process.env.LICENSE_ENCRYPTION_KEY=randomBytes(32).toString("base64");
process.env.LICENSE_SIGNING_PRIVATE_KEY=generateKeyPairSync("ed25519").privateKey.export({format:"pem",type:"pkcs8"}).toString();
process.env.RESEND_API_KEY="test";
process.env.EMAIL_FROM="test@example.invalid";
process.env.ADMIN_EMAILS="admin@example.invalid";
process.env.PAYOS_CLIENT_ID="test-client";
process.env.PAYOS_API_KEY="test-api";
process.env.PAYOS_CHECKSUM_KEY="test-checksum";

function fixture() {
  const db = new DatabaseSync(":memory:");
  const schema = readFileSync(new URL("../cloudflare/schema.sql",import.meta.url),"utf8");
  db.exec(schema); db.exec(schema);
  db.exec(readFileSync(new URL("../cloudflare/002.sql",import.meta.url),"utf8"));
  const env = { GATEWAY_SECRET:process.env.D1_GATEWAY_SECRET, DB: {
    prepare(sql: string) { return { bind(...params: any[]) { return {sql,params}; } }; },
    async batch(statements: {sql:string;params:any[]}[]) {
      db.exec("BEGIN");
      try {
        const results = statements.map(item => ({results:db.prepare(item.sql).all(...item.params)}));
        db.exec("COMMIT"); return results;
      } catch (error) { db.exec("ROLLBACK"); throw error; }
    }
  }};
  let otp="";
  const requests: {sql:string;params:unknown[]}[][]=[];
  let paymentInfo: Record<string,unknown> = {};
  mock.method(globalThis,"fetch",async(url: string | URL | Request, options: RequestInit)=> {
    if (String(url).startsWith("https://api.resend.com")) {
      otp=JSON.parse(String(options.body)).text.match(/\d{6}/)[0]; return Response.json({id:"mail-test"});
    }
    if (String(url).startsWith("https://api-merchant.payos.vn")) return Response.json({code:"00",desc:"success",data:paymentInfo});
    requests.push(JSON.parse(String(options.body)).statements);
    return worker.fetch(new Request(url,options),env);
  });
  return {db,env,requests,otp:()=>otp,payment(info:Record<string,unknown>){paymentInfo=info;},close(){mock.restoreAll();db.close();}};
}
function request(path: string, payload?: unknown, cookie="") {
  return new Request(`${process.env.APP_URL}/api/${path}`,{method:payload===undefined?"GET":"POST",
    headers:{"content-type":"application/json",origin:process.env.APP_URL!,cookie},body:payload===undefined?undefined:JSON.stringify(payload)});
}
async function paid(user: string, requestId=randomUUID()) {
  const order=await createOrderD1(user,"lifetime",requestId);
  const payment={orderCode:order.order_code,amount:200000,paymentLinkId:randomUUID(),reference:randomUUID()};
  await settlePaymentD1(payment);
  return {order,payment};
}

test("D1 gateway authenticates and rolls back entire failing batch",async()=>{
  const setup=fixture();
  try {
    assert.equal((await worker.fetch(new Request(process.env.D1_GATEWAY_URL!,{method:"POST",body:"{}"}),setup.env)).status,403);
    await assert.rejects(()=>batch([{sql:"INSERT INTO users(id,email) VALUES('rollback','rollback@test.invalid')"},guard("0"),clearGuard]),/transaction_conflict/);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM users").get()!.count,0);
    assert.throws(()=>translate("SELECT * FROM licenses FOR UPDATE"),/atomic/);
  } finally {setup.close();}
});
test("D1 OTP, sessions, profile, admin authorization and dashboard work through API",async()=>{
  const setup=fixture();
  try {
    assert.equal((await POST(request("auth/code",{email:"admin@example.invalid"}))).status,200);
    const login=await POST(request("auth/verify",{email:"admin@example.invalid",code:setup.otp()}));
    assert.equal(login.status,200,JSON.stringify(await login.clone().json()));
    const cookie=login.headers.get("set-cookie")!.split(";")[0];
    assert.equal((await POST(request("auth/verify",{email:"admin@example.invalid",code:setup.otp()}))).status,401);
    assert.equal((await POST(request("profile",{phone:"0900000000"},cookie))).status,200);
    const dashboard=await GET(request("dashboard",undefined,cookie));assert.equal(dashboard.status,200);
    assert.equal((await dashboard.json()).user.phone,"0900000000");
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,200);
    assert.equal((await GET(request("admin/overview"))).status,401);
    assert.equal((await POST(request("auth/logout",{},cookie))).status,200);
    assert.equal((await GET(request("dashboard",undefined,cookie))).status,401);
  } finally {setup.close();}
});
test("D1 concurrent orders obey cap, duplicate payments issue one key, references cannot be reused",async()=>{
  const setup=fixture(),user=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,"buyer@test.invalid"]);
    const requestId=randomUUID();
    const orders=await Promise.all(Array.from({length:4},()=>createOrderD1(user,"lifetime",requestId)));
    assert.equal(new Set(orders.map(order=>order.id)).size,1);
    assert.ok(orders[0].order_code>=1000000000);
    const payment={orderCode:orders[0].order_code,amount:200000,paymentLinkId:randomUUID(),reference:randomUUID()};
    await assert.rejects(()=>settlePaymentD1({...payment,amount:1}),/payment_mismatch/);
    await Promise.all(Array.from({length:4},()=>settlePaymentD1(payment)));
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM licenses").get()!.count,1);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM audit_log WHERE action='payment.verified'").get()!.count,1);
    const more=await Promise.allSettled(Array.from({length:8},()=>createOrderD1(user,"lifetime",randomUUID())));
    assert.equal(more.filter(result=>result.status==="fulfilled").length,5);
    const second=setup.db.prepare("SELECT order_code FROM orders WHERE status='pending'").get()!;
    await assert.rejects(()=>settlePaymentD1({...payment,orderCode:Number(second.order_code),paymentLinkId:randomUUID()}),/transaction_conflict/);
  } finally {setup.close();}
});
test("D1 license binds one installation and two slots, rejects replay, resets and revokes",async()=>{
  const setup=fixture(),user=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,"buyer@test.invalid"]);
    await paid(user);
    const record=setup.db.prepare("SELECT * FROM licenses").get()!;
    const install=generateKeyPairSync("ed25519");
    const installation=install.publicKey.export({format:"der",type:"spki"}).subarray(-32).toString("base64");
    const data={key:decrypt(String(record.key_cipher)),installation,client_id:randomUUID(),component:"custom" as "custom"|"addon",timestamp:Math.floor(Date.now()/1000),nonce:randomUUID()};
    const activate=async(payload:typeof data)=>activateLicense({...payload,signature:sign(null,Buffer.from(requestMessage(payload)),install.privateKey).toString("base64")});
    assert.ok((await activate(data)).includes("."));
    await assert.rejects(()=>activate(data),/transaction_conflict/);
    await activate({...data,nonce:randomUUID(),component:"addon",client_id:randomUUID()});
    await assert.rejects(()=>activate({...data,nonce:randomUUID(),client_id:randomUUID()}),/component_bound/);
    await adminLicenseD1(user,String(record.id),"lock");
    await assert.rejects(()=>activate({...data,nonce:randomUUID()}),/license_invalid/);
    await adminLicenseD1(user,String(record.id),"unlock");
    await adminLicenseD1(user,String(record.id),"reset");
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM activations").get()!.count,0);
    await assert.rejects(()=>activate({...data,nonce:randomUUID()}),/license_invalid/);
    assert.notEqual(setup.db.prepare("SELECT key_hash FROM licenses").get()!.key_hash,hash(data.key));
    await adminLicenseD1(user,String(record.id),"revoke");
    await assert.rejects(()=>adminLicenseD1(user,String(record.id),"reset"),/license_revoked/);
  } finally {setup.close();}
});
test("D1 manual issue is idempotent and timed plans extend",async()=>{
  const setup=fixture(),user=randomUUID(),requestId=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,"buyer@test.invalid"]);
    await d1Database.query("INSERT INTO plans(id,name,amount,duration_days) VALUES('monthly','Test',1000,30) ON CONFLICT DO NOTHING");
    await Promise.all(Array.from({length:3},()=>manualLicenseD1(user,"buyer@test.invalid","monthly",requestId)));
    const record=setup.db.prepare("SELECT * FROM licenses").get()!;
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM licenses").get()!.count,1);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM audit_log").get()!.count,1);
    await adminLicenseD1(user,String(record.id),"extend",10);
    const updated=setup.db.prepare("SELECT expires_at FROM licenses").get()!;
    assert.equal(new Date(String(updated.expires_at)).getTime()-new Date(String(record.expires_at)).getTime(),10*86400000);
  } finally {setup.close();}
});
test("D1 webhook rejects forged and unconfirmed payment, then issues once",async()=>{
  const setup=fixture(),user=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,"buyer@test.invalid"]);
    const order=await createOrderD1(user,"lifetime",randomUUID());
    const data={orderCode:order.order_code,amount:200000,description:"test",accountNumber:"test",reference:randomUUID(),transactionDateTime:"2026-09-05 12:00:00",currency:"VND",paymentLinkId:"test-link",code:"00",desc:"success",counterAccountBankId:"",counterAccountBankName:"",counterAccountName:"",counterAccountNumber:"",virtualAccountName:"",virtualAccountNumber:""};
    const signature=createHmac("sha256","test-checksum").update(Object.entries(data).sort(([left],[right])=>left.localeCompare(right)).map(([key,value])=>`${key}=${value}`).join("&")).digest("hex");
    const event={code:"00",success:true,data,signature};
    assert.equal((await POST(request("payos/webhook",{...event,signature:"forged"}))).status,400);
    setup.payment({id:"test-link",orderCode:order.order_code,amount:200000,amountPaid:0,status:"PENDING"});
    assert.equal((await POST(request("payos/webhook",event))).status,409);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM licenses").get()!.count,0);
    setup.payment({id:"test-link",orderCode:order.order_code,amount:200000,amountPaid:200000,status:"PAID"});
    const settled=await POST(request("payos/webhook",event));
    assert.equal(settled.status,200,JSON.stringify(await settled.json()));
    assert.equal((await POST(request("payos/webhook",event))).status,200);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM licenses").get()!.count,1);
  } finally {setup.close();}
});
test("D1 password signup accepts any email domain without mail and cannot claim admin",async()=>{
  const setup=fixture();
  try {
    const credentials={email:"person@another-mail.invalid",password:"Strong-password-123"};
    const created=await POST(request("auth/register",{...credentials,phone:"0900000000"}));
    assert.equal(created.status,200,JSON.stringify(await created.clone().json()));
    const cookie=created.headers.get("set-cookie")!.split(";")[0];
    const dashboard=await (await GET(request("dashboard",undefined,cookie))).json();
    assert.equal(dashboard.user.admin,false);assert.equal(dashboard.user.phone,"0900000000");
    assert.equal(setup.otp(),"");assert.ok(!JSON.stringify(dashboard).includes("password"));
    assert.equal((await POST(request("auth/register",credentials))).status,409);
    assert.equal((await POST(request("auth/register",{...credentials,email:"admin@example.invalid"}))).status,409);
    assert.equal((await POST(request("auth/register",{email:"bad@test.invalid",password:"short"}))).status,400);
    const stored=setup.db.prepare("SELECT password_hash FROM auth_credentials").get()!;
    assert.ok(String(stored.password_hash).startsWith("scrypt-v1:"));assert.ok(!String(stored.password_hash).includes(credentials.password));
    assert.equal((await POST(request("auth/login",{...credentials,password:"incorrect-password"}))).status,401);
    assert.equal((await POST(request("auth/login",credentials))).status,200);
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,403);
    setup.db.prepare("UPDATE users SET email='admin@example.invalid'").run();
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,403);
  } finally {setup.close();}
});
test("D1 trial is once per account and installation, starts on activation and survives resets",async()=>{
  const setup=fixture(),user=randomUUID(),other=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2),($3,$4)",[user,"trial@test.invalid",other,"other@test.invalid"]);
    const ids=await Promise.all(Array.from({length:4},()=>claimTrial(user)));
    assert.equal(new Set(ids).size,1);
    let record=setup.db.prepare("SELECT * FROM licenses WHERE id=?").get(ids[0])!;
    assert.equal(record.expires_at,null);
    const install=generateKeyPairSync("ed25519"),installation=install.publicKey.export({format:"der",type:"spki"}).subarray(-32).toString("base64");
    const custom=randomUUID(),addon=randomUUID();
    async function activate(key:string,component:"custom"|"addon"="custom",identity=install) {
      const payload={key,installation:identity.publicKey.export({format:"der",type:"spki"}).subarray(-32).toString("base64"),client_id:component==="custom"?custom:addon,component,timestamp:Math.floor(Date.now()/1000),nonce:randomUUID()};
      return activateLicense({...payload,signature:sign(null,Buffer.from(requestMessage(payload)),identity.privateKey).toString("base64")});
    }
    const key=decrypt(String(record.key_cipher));
    const lease=await activate(key), payload=JSON.parse(Buffer.from(lease.split(".")[0],"base64url").toString());
    assert.ok(payload.exp-payload.iat<=86400);assert.ok(payload.exp-payload.iat>=86398);
    await activate(key,"addon");
    record=setup.db.prepare("SELECT * FROM licenses WHERE id=?").get(ids[0])!;
    const originalExpiry=record.expires_at;
    const secondId=await claimTrial(other),second=setup.db.prepare("SELECT * FROM licenses WHERE id=?").get(secondId)!;
    await assert.rejects(()=>activate(decrypt(String(second.key_cipher))),/trial_already_used/);
    await assert.rejects(()=>adminLicenseD1(user,ids[0],"extend",1),/cannot_extend_trial/);
    await adminLicenseD1(user,ids[0],"reset");
    const reset=setup.db.prepare("SELECT * FROM licenses WHERE id=?").get(ids[0])!;
    const resetKey=decrypt(String(reset.key_cipher));
    await assert.rejects(()=>activate(resetKey,"custom",generateKeyPairSync("ed25519")),/trial_already_used/);
    await activate(resetKey);assert.equal(reset.expires_at,originalExpiry);
    await manualLicense(user,"trial@test.invalid","trial",randomUUID());
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM trial_claims WHERE user_id=?").get(user)!.count,1);
    setup.db.prepare("UPDATE licenses SET expires_at='2000-01-01T00:00:00.000Z' WHERE id=?").run(ids[0]);
    assert.equal(await claimTrial(user),ids[0]);
    await assert.rejects(()=>activate(resetKey),/license_invalid/);
    await adminLicenseD1(user,ids[0],"revoke");
    assert.equal(setup.db.prepare("SELECT license_id FROM trial_installations WHERE installation_key=?").get(installation)!.license_id,ids[0]);
    await assert.rejects(()=>activate(decrypt(String(second.key_cipher))),/trial_already_used/);
    await assert.rejects(()=>createOrderD1(user,"trial",randomUUID()),/use_trial_endpoint/);
  } finally {setup.close();}
});
test("D1 simultaneous accounts cannot trial on the same installation",async()=>{
  const setup=fixture();
  try {
    const identity=generateKeyPairSync("ed25519"),installation=identity.publicKey.export({format:"der",type:"spki"}).subarray(-32).toString("base64");
    const keys:string[]=[];
    for (let index=0;index<2;index++) {
      const user=randomUUID();await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,`${index}@test.invalid`]);
      const id=await claimTrial(user);keys.push(decrypt(String(setup.db.prepare("SELECT key_cipher FROM licenses WHERE id=?").get(id)!.key_cipher)));
    }
    const result=await Promise.allSettled(keys.map(key=>{
      const payload={key,installation,component:"custom" as const,client_id:randomUUID(),timestamp:Math.floor(Date.now()/1000),nonce:randomUUID()};
      return activateLicense({...payload,signature:sign(null,Buffer.from(requestMessage(payload)),identity.privateKey).toString("base64")});
    }));
    assert.equal(result.filter(item=>item.status==="fulfilled").length,1);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM trial_installations").get()!.count,1);
  } finally {setup.close();}
});
test("D1 monthly price and 30-day expiry come from server, migration preserves existing data",async()=>{
  const setup=fixture(),user=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,$2)",[user,"monthly@test.invalid"]);
    const order=await createOrderD1(user,"monthly",randomUUID());assert.equal(order.amount,50000);
    await settlePaymentD1({orderCode:order.order_code,amount:50000,paymentLinkId:randomUUID(),reference:randomUUID()});
    const license=setup.db.prepare("SELECT * FROM licenses").get()!;
    const remaining=new Date(String(license.expires_at)).getTime()-Date.now();
    assert.ok(remaining<=30*86400000 && remaining>30*86400000-5000);
    setup.db.exec("BEGIN");setup.db.exec(readFileSync(new URL("../cloudflare/002.sql",import.meta.url),"utf8"));setup.db.exec("COMMIT");
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM licenses").get()!.count,1);
    assert.equal(setup.db.prepare("PRAGMA foreign_key_check").all().length,0);
    assert.deepEqual((await d1Database.query("SELECT amount FROM plans ORDER BY amount")).rows.map(row=>row.amount),[0,50000,200000]);
  } finally {setup.close();}
});
test("D1 password change checks current password, rotates sessions and preserves licenses",async()=>{
  const setup=fixture();
  try {
    const credentials={email:"change@test.invalid",password:"original-password-123"};
    const created=await POST(request("auth/register",credentials));assert.equal(created.status,200);
    const cookie=created.headers.get("set-cookie")!.split(";")[0];
    const second=await POST(request("auth/login",credentials));const secondCookie=second.headers.get("set-cookie")!.split(";")[0];
    await POST(request("licenses/trial",{},cookie));
    const before=await (await GET(request("dashboard",undefined,cookie))).json();
    const payload={current_password:credentials.password,new_password:"updated-password-456",confirm_password:"updated-password-456"};
    assert.equal((await POST(request("auth/password",payload))).status,401);
    const forged=request("auth/password",payload,cookie);forged.headers.set("origin","https://attacker.invalid");
    assert.equal((await POST(forged)).status,403);
    assert.equal((await POST(request("auth/password",{...payload,confirm_password:"different-password"},cookie))).status,400);
    assert.equal((await POST(request("auth/password",{...payload,current_password:"wrong-password-123"},cookie))).status,400);
    assert.equal((await POST(request("auth/password",{current_password:credentials.password,new_password:credentials.password,confirm_password:credentials.password},cookie))).status,400);
    assert.equal((await GET(request("dashboard",undefined,secondCookie))).status,200);
    const result=await POST(request("auth/password",payload,cookie));assert.equal(result.status,200,JSON.stringify(await result.clone().json()));
    assert.equal(await result.text(),'{"success":true}');
    const replacement=result.headers.get("set-cookie")!.split(";")[0];assert.notEqual(replacement,cookie);
    assert.equal((await GET(request("dashboard",undefined,cookie))).status,401);
    assert.equal((await GET(request("dashboard",undefined,secondCookie))).status,401);
    const after=await (await GET(request("dashboard",undefined,replacement))).json();assert.deepEqual(after.licenses,before.licenses);assert.equal(after.trial_claimed,true);
    assert.equal((await POST(request("auth/login",credentials))).status,401);
    assert.equal((await POST(request("auth/login",{...credentials,password:payload.new_password}))).status,200);
    const audits=setup.db.prepare("SELECT * FROM audit_log WHERE action='account.password_changed'").all();assert.equal(audits.length,1);
    assert.ok(!JSON.stringify(audits).includes(payload.new_password));
  } finally {setup.close();}
});
test("D1 simultaneous password changes allow one winner and reject stale session",async()=>{
  const setup=fixture();
  try {
    const created=await POST(request("auth/register",{email:"race@test.invalid",password:"original-password-123"}));
    const cookie=created.headers.get("set-cookie")!.split(";")[0],digest=hash(cookie.slice("rd_session=".length));
    const user=setup.db.prepare("SELECT id FROM users").get()!;
    const changes=await Promise.allSettled([
      changePassword(String(user.id),"original-password-123","first-password-long",digest),
      changePassword(String(user.id),"original-password-123","second-password-long",digest),
    ]);
    assert.equal(changes.filter(item=>item.status==="fulfilled").length,1);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM sessions").get()!.count,1);
    assert.equal(setup.db.prepare("SELECT count(*) AS count FROM audit_log WHERE action='account.password_changed'").get()!.count,1);
  } finally {setup.close();}
});
test("D1 dashboard and admin reads each use one data batch and never cache private responses",async()=>{
  const setup=fixture(),user=randomUUID();
  try {
    await d1Database.query("INSERT INTO users(id,email) VALUES($1,'admin@test.invalid')",[user]);
    await d1Database.query("INSERT INTO administrator_accounts VALUES($1)",[user]);
    await d1Database.query("INSERT INTO sessions VALUES($1,$2,now()+interval '1 day')",[hash("read-session"),user]);
    const start=setup.requests.length;
    const response=await GET(request("dashboard",undefined,"rd_session=read-session"));assert.equal(response.status,200);
    assert.equal(response.headers.get("cache-control"),"no-store");
    assert.equal(setup.requests.length-start,3);
    assert.equal(setup.requests.at(-1)!.length,3);
    const beforeAdmin=setup.requests.length;
    assert.equal((await GET(request("admin/overview",undefined,"rd_session=read-session"))).status,200);
    assert.equal(setup.requests.length-beforeAdmin,4);
    assert.equal(setup.requests.at(-1)!.length,6);
  } finally {setup.close();}
});
