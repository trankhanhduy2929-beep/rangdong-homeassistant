import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHmac, generateKeyPairSync, randomUUID, sign } from "node:crypto";
import { PGlite } from "@electric-sql/pglite";
import { database } from "../lib/db";
import { hash, encrypt, newLicense } from "../lib/security";
import { requestMessage } from "../lib/licenses";
import { GET, POST } from "../app/api/[...path]/route";
import { claimTrial } from "../lib/trials";
import { activateLicense } from "../lib/licenses";
import { decrypt } from "../lib/security";

process.env.DATABASE_URL="postgresql://test:test@localhost/test";
process.env.APP_URL="https://license.example.invalid";
process.env.AUTH_SECRET="test-secret-for-automated-tests-only";
process.env.RESEND_API_KEY="test-resend-key";
process.env.EMAIL_FROM="test@example.invalid";
process.env.ADMIN_EMAILS="admin@example.invalid";
process.env.PAYOS_CLIENT_ID="test-client";
process.env.PAYOS_API_KEY="test-api";
process.env.PAYOS_CHECKSUM_KEY="test-checksum";
process.env.LICENSE_ENCRYPTION_KEY=Buffer.alloc(32,23).toString("base64");
process.env.LICENSE_SIGNING_PRIVATE_KEY=generateKeyPairSync("ed25519").privateKey.export({type:"pkcs8",format:"pem"}).toString();

function request(path:string,payload?:unknown,cookie?:string,origin="https://license.example.invalid"){
  return new Request(`https://license.example.invalid/api/${path}`,{method:payload===undefined?"GET":"POST",
    headers:{"Content-Type":"application/json",Origin:origin,...(cookie?{Cookie:cookie}:{})},body:payload===undefined?undefined:JSON.stringify(payload)});
}
async function fixture(){
  const embedded=new PGlite();await embedded.exec(await readFile(new URL("../db/001.sql",import.meta.url),"utf8"));
  await embedded.exec(await readFile(new URL("../db/002.sql",import.meta.url),"utf8"));
  const pool=database();
  const query=(text:string,parameters?:unknown[])=>embedded.query(text,parameters);
  mock.method(pool,"query",query);
  mock.method(pool,"connect",async()=>({query,release(){}}));
  return embedded;
}
function signature(data:Record<string,unknown>){
  return createHmac("sha256","test-checksum").update(Object.keys(data).sort().map(key=>`${key}=${data[key]??""}`).join("&")).digest("hex");
}
test("PostgreSQL password change invalidates all old sessions without changing trial",async()=>{
  const embedded=await fixture();
  try {
    const credentials={email:"change@postgres.invalid",password:"original-password-123"};
    const registered=await POST(request("auth/register",credentials));
    const cookie=registered.headers.get("set-cookie")!.split(";")[0];
    await POST(request("licenses/trial",{},cookie));
    const before=await (await GET(request("dashboard",undefined,cookie))).json();
    const payload={current_password:credentials.password,new_password:"updated-password-456",confirm_password:"updated-password-456"};
    assert.equal((await POST(request("auth/password",{...payload,current_password:"incorrect-password"},cookie))).status,400);
    const changed=await POST(request("auth/password",payload,cookie));assert.equal(changed.status,200,JSON.stringify(await changed.clone().json()));
    const replacement=changed.headers.get("set-cookie")!.split(";")[0];
    assert.equal((await GET(request("dashboard",undefined,cookie))).status,401);
    const after=await (await GET(request("dashboard",undefined,replacement))).json();assert.deepEqual(after.licenses,before.licenses);
    assert.equal((await POST(request("auth/login",credentials))).status,401);
    assert.equal((await POST(request("auth/login",{...credentials,password:payload.new_password}))).status,200);
  }finally{mock.restoreAll();await embedded.close();}
});
test("PostgreSQL password accounts and once-only trial installation follow the same policy",async()=>{
  const embedded=await fixture();
  try {
    const credentials={email:"password@any-domain.invalid",password:"test-password-long-enough"};
    const response=await POST(request("auth/register",credentials));assert.equal(response.status,200,JSON.stringify(await response.clone().json()));
    const cookie=response.headers.get("set-cookie")!.split(";")[0];
    assert.equal((await POST(request("auth/login",credentials))).status,200);
    assert.equal((await POST(request("auth/register",{...credentials,email:"admin@example.invalid"}))).status,409);
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,403);
    const user=(await embedded.query<{id:string}>("SELECT id FROM users WHERE email=$1",[credentials.email])).rows[0];
    const licenseId=await claimTrial(user.id);assert.equal(await claimTrial(user.id),licenseId);
    const key=decrypt((await embedded.query<{key_cipher:string}>("SELECT key_cipher FROM licenses WHERE id=$1",[licenseId])).rows[0].key_cipher);
    const install=generateKeyPairSync("ed25519"),installation=install.publicKey.export({format:"der",type:"spki"}).subarray(-32).toString("base64");
    async function activate(licenseKey:string,component:"custom"|"addon") {
      const data={key:licenseKey,installation,client_id:randomUUID(),component,timestamp:Math.floor(Date.now()/1000),nonce:randomUUID()};
      return activateLicense({...data,signature:sign(null,Buffer.from(requestMessage(data)),install.privateKey).toString("base64")});
    }
    await activate(key,"custom");await activate(key,"addon");
    const other=randomUUID();await embedded.query("INSERT INTO users(id,email) VALUES($1,'other@test.invalid')",[other]);
    const second=await claimTrial(other),secondKey=decrypt((await embedded.query<{key_cipher:string}>("SELECT key_cipher FROM licenses WHERE id=$1",[second])).rows[0].key_cipher);
    await assert.rejects(()=>activate(secondKey,"custom"),/trial_already_used/);
    const expiry=(await embedded.query<{expires_at:Date}>("SELECT expires_at FROM licenses WHERE id=$1",[licenseId])).rows[0].expires_at;
    assert.ok(new Date(expiry).getTime()-Date.now()<=86400000);
  }finally{mock.restoreAll();await embedded.close();}
});

test("email OTP signup/login, replay prevention, profile and admin authorization",async()=>{
  const embedded=await fixture();let otp="";
  mock.method(globalThis,"fetch",async (_url:unknown,options:RequestInit)=>{
    const email=JSON.parse(options.body as string);otp=email.text.match(/\d{6}/)[0];return Response.json({id:"email-test"});
  });
  try{
    assert.equal((await POST(request("auth/code",{email:"person@example.invalid"}))).status,200);
    const verified=await POST(request("auth/verify",{email:"person@example.invalid",code:otp}));assert.equal(verified.status,200);
    const cookie=verified.headers.get("set-cookie")!.split(";")[0];assert.ok(verified.headers.get("set-cookie")!.includes("HttpOnly"));
    assert.equal((await POST(request("auth/verify",{email:"person@example.invalid",code:otp}))).status,401);
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,403);
    assert.equal((await POST(request("profile",{phone:"0900000000"},cookie,"https://attacker.invalid"))).status,403);
    assert.equal((await POST(request("profile",{phone:"0900000000"},cookie))).status,200);
    assert.equal((await (await GET(request("dashboard",undefined,cookie))).json()).user.phone,"0900000000");
    assert.equal((await POST(request("auth/logout",{},cookie))).status,200);
    assert.equal((await GET(request("dashboard",undefined,cookie))).status,401);
  }finally{mock.restoreAll();await embedded.close();}
});

test("signed webhook verifies provider state, issues once, and never trusts browser return",async()=>{
  const embedded=await fixture();const user=randomUUID(),order=randomUUID();
  await embedded.query("INSERT INTO users(id,email) VALUES($1,'buyer@example.invalid')",[user]);
  await embedded.query("INSERT INTO orders(id,user_id,plan_id,amount,request_id,order_code,payment_link_id) VALUES($1,$2,'lifetime',200000,$3,1234567890,'payment-test')",[order,user,randomUUID()]);
  const data={orderCode:1234567890,amount:200000,description:"RD1234567890",accountNumber:"test-account",reference:"txn-test",transactionDateTime:"2026-09-05 12:00:00",currency:"VND",paymentLinkId:"payment-test",code:"00",desc:"success",counterAccountBankId:"",counterAccountBankName:"",counterAccountName:"",counterAccountNumber:"",virtualAccountName:"",virtualAccountNumber:""};
  mock.method(globalThis,"fetch",async()=>Response.json({code:"00",desc:"success",data:{id:"payment-test",orderCode:1234567890,amount:200000,amountPaid:200000,status:"PAID",amountRemaining:0,transactions:[]}}));
  try{
    assert.equal((await POST(request("payos/webhook",{code:"00",success:true,data,signature:"forged"}))).status,400);
    assert.equal((await GET(request("dashboard?order="+order+"&status=PAID"))).status,401);
    assert.equal((await embedded.query<{count:number}>("SELECT count(*)::int AS count FROM licenses")).rows[0].count,0);
    const event={code:"00",desc:"success",success:true,data,signature:signature(data)};
    const wrongAmount={...data,amount:199000};
    assert.equal((await POST(request("payos/webhook",{...event,data:wrongAmount,signature:signature(wrongAmount)}))).status,409);
    const first=await POST(request("payos/webhook",event));assert.equal(first.status,200,JSON.stringify(await first.json()));
    assert.equal((await POST(request("payos/webhook",event))).status,200);
    assert.equal((await embedded.query<{count:number}>("SELECT count(*)::int AS count FROM licenses")).rows[0].count,1);
  }finally{mock.restoreAll();await embedded.close();}
});

test("checkout price comes from plan and repeated requests reuse one order",async()=>{
  const embedded=await fixture(),user=randomUUID();
  await embedded.query("INSERT INTO users(id,email) VALUES($1,'buyer@example.invalid')",[user]);
  await embedded.query("INSERT INTO sessions VALUES($1,$2,now()+interval '1 day')",[hash("buyer-session"),user]);
  let creations=0;
  mock.method(globalThis,"fetch",async(_url:unknown,options:RequestInit)=>{
    const request=JSON.parse(options.body as string);creations++;assert.equal(request.amount,200000);
    return Response.json({code:"00",desc:"success",data:{bin:"test",accountNumber:"test",accountName:"test",amount:200000,description:request.description,orderCode:request.orderCode,currency:"VND",paymentLinkId:"new-payment",status:"PENDING",checkoutUrl:"https://pay.payos.vn/web/new-payment",qrCode:"test-qr"}});
  });
  try{
    const payload={plan_id:"lifetime",request_id:randomUUID(),amount:1};
    const first=await POST(request("orders",payload,"rd_session=buyer-session"));assert.equal(first.status,200,JSON.stringify(await first.json()));
    assert.equal((await POST(request("orders",payload,"rd_session=buyer-session"))).status,200);
    assert.equal(creations,1);
    assert.equal((await embedded.query<{count:number}>("SELECT count(*)::int AS count FROM orders")).rows[0].count,1);
  }finally{mock.restoreAll();await embedded.close();}
});

test("admin manual key idempotency, reset rotation, lock/unlock/revoke and audit",async()=>{
  const embedded=await fixture(),admin=randomUUID(),user=randomUUID();
  await embedded.query("INSERT INTO users(id,email) VALUES($1,'admin@example.invalid'),($2,'user@example.invalid')",[admin,user]);
  await embedded.query("INSERT INTO administrator_accounts(user_id) VALUES($1)",[admin]);
  await embedded.query("INSERT INTO sessions VALUES($1,$2,now()+interval '1 day')",[hash("admin-session"),admin]);
  const cookie="rd_session=admin-session";
  try{
    const payload={email:"user@example.invalid",plan_id:"lifetime",request_id:randomUUID()};
    assert.equal((await POST(request("admin/manual",payload,cookie))).status,200);
    assert.equal((await POST(request("admin/manual",payload,cookie))).status,200);
    const first=(await embedded.query<{id:string;key_hash:string}>("SELECT id,key_hash FROM licenses")).rows[0];
    assert.equal((await embedded.query<{count:number}>("SELECT count(*)::int AS count FROM licenses")).rows[0].count,1);
    assert.equal((await POST(request("admin/license",{id:first.id,action:"reset"},cookie))).status,200);
    assert.notEqual((await embedded.query<{key_hash:string}>("SELECT key_hash FROM licenses")).rows[0].key_hash,first.key_hash);
    for(const [action,status] of [["lock","locked"],["unlock","active"],["revoke","revoked"]]){
      assert.equal((await POST(request("admin/license",{id:first.id,action},cookie))).status,200);
      assert.equal((await embedded.query<{status:string}>("SELECT status FROM licenses")).rows[0].status,status);
    }
    assert.ok((await embedded.query<{count:number}>("SELECT count(*)::int AS count FROM audit_log")).rows[0].count>=5);
    assert.equal((await GET(request("admin/overview",undefined,cookie))).status,200);
  }finally{mock.restoreAll();await embedded.close();}
});

test("license endpoint requires proof, rejects replay and another installation",async()=>{
  const embedded=await fixture(),user=randomUUID(),key=newLicense();
  await embedded.query("INSERT INTO users(id,email) VALUES($1,'owner@example.invalid')",[user]);
  await embedded.query("INSERT INTO licenses(id,user_id,plan_id,key_hash,key_cipher) VALUES($1,$2,'lifetime',$3,$4)",[randomUUID(),user,hash(key),encrypt(key)]);
  const identity=generateKeyPairSync("ed25519");
  const data={key,installation:identity.publicKey.export({type:"spki",format:"der"}).subarray(-32).toString("base64"),client_id:randomUUID(),component:"custom" as const,timestamp:Math.floor(Date.now()/1000),nonce:randomUUID()};
  const payload={...data,signature:sign(null,Buffer.from(requestMessage(data)),identity.privateKey).toString("base64")};
  try{
    assert.equal((await POST(request("licenses/activate",{...payload,signature:"forged"}))).status,401);
    assert.equal((await POST(request("licenses/activate",payload))).status,200);
    assert.equal((await POST(request("licenses/activate",payload))).status,409);
    const other=generateKeyPairSync("ed25519"),second={...data,installation:other.publicKey.export({type:"spki",format:"der"}).subarray(-32).toString("base64"),nonce:randomUUID()};
    assert.equal((await POST(request("licenses/activate",{...second,signature:sign(null,Buffer.from(requestMessage(second)),other.privateKey).toString("base64")}))).status,409);
  }finally{mock.restoreAll();await embedded.close();}
});
