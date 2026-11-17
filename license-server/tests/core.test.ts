import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { generateKeyPairSync, randomUUID, sign, verify } from "node:crypto";
import { PGlite } from "@electric-sql/pglite";
import type { PoolClient } from "pg";
import { settlePayment } from "../lib/payments";
import { bindLicense, requestMessage } from "../lib/licenses";
import { decrypt, encrypt, hash, newLicense, verifyInstallation } from "../lib/security";

const server=generateKeyPairSync("ed25519");
process.env.LICENSE_ENCRYPTION_KEY=Buffer.alloc(32,37).toString("base64");
process.env.LICENSE_SIGNING_PRIVATE_KEY=server.privateKey.export({type:"pkcs8",format:"pem"}).toString();
const install=generateKeyPairSync("ed25519");
const publicKey=install.publicKey.export({type:"spki",format:"der"}).subarray(-32).toString("base64");

async function fixture(){
  const database=new PGlite();await database.exec(await readFile(new URL("../db/001.sql",import.meta.url),"utf8"));
  await database.exec(await readFile(new URL("../db/002.sql",import.meta.url),"utf8"));
  const user=randomUUID(),order=randomUUID();
  await database.query("INSERT INTO users(id,email) VALUES($1,'test@example.invalid')",[user]);
  await database.query("INSERT INTO orders(id,user_id,plan_id,amount,request_id,order_code,payment_link_id) VALUES($1,$2,'lifetime',200000,$3,1234567890,'test-payment')",[order,user,randomUUID()]);
  return {database,user,order,client:database as unknown as PoolClient};
}
const payment={orderCode:1234567890,amount:200000,paymentLinkId:"test-payment",reference:"unique-reference"};

test("license material encrypted and tampering rejected",()=>{
  const key=newLicense();const cipher=encrypt(key);assert.equal(decrypt(cipher),key);assert.ok(!cipher.includes(key));
  assert.throws(()=>decrypt(cipher.slice(0,-4)+"AAAA"));
});
test("installation proof binds entire request",()=>{
  const data={key:newLicense(),installation:publicKey,client_id:randomUUID(),component:"custom" as const,timestamp:123,nonce:randomUUID()};
  const message=requestMessage(data),signature=sign(null,Buffer.from(message),install.privateKey).toString("base64");
  assert.equal(verifyInstallation(message,signature,publicKey),true);
  assert.equal(verifyInstallation(message+"tampered",signature,publicKey),false);
});
test("duplicate confirmed payments only issue one lifetime license",async()=>{
  const {database,client}=await fixture();
  try{
    await database.exec("BEGIN");await settlePayment(client,payment);await database.exec("COMMIT");
    await database.exec("BEGIN");await settlePayment(client,payment);await database.exec("COMMIT");
    const result=await database.query<{count:number}>("SELECT count(*)::integer AS count FROM licenses");assert.equal(result.rows[0].count,1);
    const orders=await database.query<{status:string}>("SELECT status FROM orders");assert.equal(orders.rows[0].status,"paid");
    const records=await database.query<{expires_at:unknown;key_cipher:string}>("SELECT expires_at,key_cipher FROM licenses");assert.equal(records.rows[0].expires_at,null);assert.match(decrypt(records.rows[0].key_cipher),/^RD-/);
  }finally{await database.close();}
});
test("wrong amount and wrong PayOS link never issue a license",async()=>{
  const {database,client}=await fixture();
  try{
    await assert.rejects(()=>settlePayment(client,{...payment,amount:1000}),/payment_mismatch/);
    await assert.rejects(()=>settlePayment(client,{...payment,paymentLinkId:"wrong-link"}),/payment_mismatch/);
    const result=await database.query<{count:number}>("SELECT count(*)::integer AS count FROM licenses");assert.equal(result.rows[0].count,0);
  }finally{await database.close();}
});
test("payment rollback cannot leave a paid order without a key",async()=>{
  const {database,client}=await fixture();
  try{
    await database.exec("BEGIN");await settlePayment(client,payment);await database.exec("ROLLBACK");
    assert.equal((await database.query<{status:string}>("SELECT status FROM orders")).rows[0].status,"pending");
    assert.equal((await database.query<{count:number}>("SELECT count(*)::integer AS count FROM licenses")).rows[0].count,0);
  }finally{await database.close();}
});
test("one installation, one custom slot, one addon slot, signed leases",async()=>{
  const {database,client}=await fixture();
  try{
    await settlePayment(client,payment);
    const record=(await database.query<{key_cipher:string}>("SELECT key_cipher FROM licenses")).rows[0];
    const data={key:decrypt(record.key_cipher),installation:publicKey,component:"custom" as const,client_id:randomUUID(),timestamp:123,nonce:randomUUID(),signature:"unused-in-db-test"};
    const token=await bindLicense(client,data);const [encoded,signature]=token.split(".");
    assert.equal(verify(null,Buffer.from(encoded),server.publicKey,Buffer.from(signature,"base64url")),true);
    await bindLicense(client,data);
    await bindLicense(client,{...data,component:"addon",client_id:randomUUID()});
    await assert.rejects(()=>bindLicense(client,{...data,installation:Buffer.alloc(32,1).toString("base64")}),/license_bound/);
    await assert.rejects(()=>bindLicense(client,{...data,client_id:randomUUID()}),/component_bound/);
    await database.query("UPDATE licenses SET status='locked'");
    await assert.rejects(()=>bindLicense(client,data),/license_invalid/);
    await database.query("UPDATE licenses SET status='revoked'");
    await assert.rejects(()=>bindLicense(client,data),/license_invalid/);
    await database.query("UPDATE licenses SET status='active',expires_at=now()-interval '1 second'");
    await assert.rejects(()=>bindLicense(client,data),/license_invalid/);
  }finally{await database.close();}
});
test("database constraints reject duplicate slots and reused transaction reference",async()=>{
  const {database,client,user}=await fixture();
  try{
    await settlePayment(client,payment);
    const second=randomUUID();await database.query("INSERT INTO orders(id,user_id,plan_id,amount,request_id,order_code,payment_link_id) VALUES($1,$2,'lifetime',200000,$3,1234567891,'second-link')",[second,user,randomUUID()]);
    await assert.rejects(()=>settlePayment(client,{...payment,orderCode:1234567891,paymentLinkId:"second-link"}),/payment_reference_conflict/);
    const key=newLicense();assert.equal(hash(key).length,64);
  }finally{await database.close();}
});
