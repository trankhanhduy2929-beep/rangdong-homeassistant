import { randomBytes, randomUUID } from "node:crypto";
import { batch, clearGuard, d1Database, guard, nowSQL, afterSQL, type Statement } from "./d1-client";
import { digestCode, encrypt, hash, lease, newLicense, PublicError } from "./security";
import type { Activation } from "./licenses";
import type { VerifiedPayment } from "./payments";

export async function verifyCodeD1(email: string, code: string, admin=false) {
  const token = randomBytes(32).toString("base64url");
  const digest = digestCode(email, code);
  const valid = (await d1Database.query("SELECT email FROM email_codes WHERE email=$1 AND digest=$2 AND expires_at>now()", [email, digest])).rows[0];
  if (!valid) throw new PublicError("invalid_code", 401);
  await batch([
    guard(`EXISTS(SELECT 1 FROM email_codes WHERE email=? AND digest=? AND expires_at>${nowSQL})`, [email,digest]),
    { sql: "INSERT INTO users(id,email) VALUES(?,?) ON CONFLICT(email) DO NOTHING", params: [randomUUID(),email] },
    ...(admin?[{sql:"INSERT INTO administrator_accounts(user_id) SELECT id FROM users WHERE email=? ON CONFLICT DO NOTHING",params:[email]}]:[]),
    { sql: `INSERT INTO sessions(digest,user_id,expires_at) SELECT ?,id,${afterSQL("'+7 days'")} FROM users WHERE email=?`, params: [hash(token),email] },
    { sql: "DELETE FROM email_codes WHERE email=? AND digest=?", params: [email,digest] }, clearGuard,
  ]);
  return token;
}

export async function createOrderD1(userId: string, planId: string, requestId: string) {
  if (planId === "trial") throw new PublicError("use_trial_endpoint");
  const result = await batch([
    guard(`EXISTS(SELECT 1 FROM orders WHERE user_id=? AND request_id=?) OR
      ((SELECT count(*) FROM orders WHERE user_id=? AND status='pending' AND created_at>${afterSQL("'-24 hours'")})<5
      AND EXISTS(SELECT 1 FROM plans WHERE id=? AND active=1 AND amount>0))`, [userId,requestId,userId,planId]),
    { sql: `INSERT INTO orders(id,user_id,plan_id,amount,duration_days,request_id)
      SELECT ?,?,id,amount,duration_days,? FROM plans WHERE id=? AND active=1 AND amount>0
      ON CONFLICT(user_id,request_id) DO NOTHING`, params: [randomUUID(),userId,requestId,planId] },
    { sql: "SELECT * FROM orders WHERE user_id=? AND request_id=?", params: [userId,requestId] }, clearGuard,
  ]);
  if (!result[2].rows[0]) throw new PublicError("invalid_plan");
  return result[2].rows[0];
}

export async function settlePaymentD1(payment: VerifiedPayment) {
  const key = newLicense();
  const record = (await d1Database.query("SELECT * FROM orders WHERE order_code=$1", [payment.orderCode])).rows[0];
  if (!record) return false;
  if (record.amount !== payment.amount || (record.payment_link_id && record.payment_link_id !== payment.paymentLinkId)) throw new PublicError("payment_mismatch",400);
  await batch([
    guard("EXISTS(SELECT 1 FROM orders WHERE order_code=? AND amount=? AND (payment_link_id IS NULL OR payment_link_id=?))", [payment.orderCode,payment.amount,payment.paymentLinkId]),
    guard("NOT EXISTS(SELECT 1 FROM payments WHERE reference=? AND order_id<>?)", [payment.reference,record.id]),
    { sql: `INSERT INTO payments(reference,order_id,payment_link_id,amount)
      SELECT ?,id,?,amount FROM orders WHERE id=? AND status<>'paid' ON CONFLICT(reference) DO NOTHING`, params: [payment.reference,payment.paymentLinkId,record.id] },
    { sql: `INSERT INTO licenses(id,user_id,plan_id,order_id,key_hash,key_cipher,expires_at)
      SELECT ?,user_id,plan_id,id,?,?,CASE WHEN duration_days IS NULL THEN NULL ELSE ${afterSQL("'+' || duration_days || ' days'")} END
      FROM orders WHERE id=? AND status<>'paid' ON CONFLICT(order_id) DO NOTHING`, params: [randomUUID(),hash(key),encrypt(key),record.id] },
    { sql: "INSERT INTO audit_log(id,action,target_id) SELECT ?,'payment.verified',id FROM orders WHERE id=? AND status<>'paid'", params: [randomUUID(),record.id] },
    { sql: `UPDATE orders SET status='paid',paid_at=${nowSQL},payment_link_id=? WHERE id=? AND status<>'paid'`, params: [payment.paymentLinkId,record.id] }, clearGuard,
  ]);
  return true;
}

export async function activateD1(data: Activation) {
  const record = (await d1Database.query("SELECT * FROM licenses WHERE key_hash=$1",[hash(data.key)])).rows[0];
  if (!record || record.status !== "active" || (record.expires_at && new Date(record.expires_at).getTime()<=Date.now())) throw new PublicError("license_invalid",403);
  if (record.installation_key && record.installation_key!==data.installation) throw new PublicError("license_bound",409);
  const slot = (await d1Database.query("SELECT client_id FROM activations WHERE license_id=$1 AND component=$2",[record.id,data.component])).rows[0];
  if (slot && slot.client_id!==data.client_id) throw new PublicError("component_bound",409);
  const trialStatements: Statement[] = [];
  if (record.plan_id === "trial") {
    const previous=(await d1Database.query("SELECT installation_key,license_id FROM trial_installations WHERE installation_key=$1 OR license_id=$2",[data.installation,record.id])).rows;
    if (previous.some(item=>item.license_id!==record.id || item.installation_key!==data.installation)) throw new PublicError("trial_already_used",409);
    trialStatements.push(
      guard("NOT EXISTS(SELECT 1 FROM trial_installations WHERE (installation_key=? AND license_id<>?) OR (license_id=? AND installation_key<>?))",[data.installation,record.id,record.id,data.installation]),
      {sql:"INSERT INTO trial_installations(installation_key,license_id) VALUES(?,?) ON CONFLICT(installation_key) DO NOTHING",params:[data.installation,record.id]},
      {sql:`UPDATE licenses SET expires_at=coalesce(expires_at,${afterSQL("'+1 day'")}) WHERE id=?`,params:[record.id]},
    );
  }
  const results = await batch([
    { sql: `DELETE FROM license_nonces WHERE expires_at<${nowSQL}` },
    { sql: `INSERT INTO license_nonces VALUES(?,${afterSQL("'+10 minutes'")})`, params: [hash(`${data.installation}:${data.nonce}`)] },
    guard(`EXISTS(SELECT 1 FROM licenses WHERE id=? AND key_hash=? AND status='active' AND (expires_at IS NULL OR expires_at>${nowSQL}) AND (installation_key IS NULL OR installation_key=?))`, [record.id,hash(data.key),data.installation]),
    guard("NOT EXISTS(SELECT 1 FROM activations WHERE license_id=? AND component=? AND client_id<>?)", [record.id,data.component,data.client_id]),
    ...trialStatements,
    { sql: "UPDATE licenses SET installation_key=? WHERE id=?", params: [data.installation,record.id] },
    { sql: `INSERT INTO activations(license_id,component,client_id) VALUES(?,?,?) ON CONFLICT(license_id,component) DO UPDATE SET last_seen=${nowSQL}`, params: [record.id,data.component,data.client_id] },
    { sql: "SELECT * FROM licenses WHERE id=?", params: [record.id] }, clearGuard,
  ]);
  const bound = results[results.length-2].rows[0], now = Math.floor(Date.now()/1000);
  return lease({v:1,license_id:bound.id,installation:data.installation,client_id:data.client_id,component:data.component,
    generation:bound.generation,iat:now,exp:Math.min(now+72*3600,bound.expires_at ? Math.floor(new Date(bound.expires_at).getTime()/1000) : now+72*3600)});
}

export async function adminLicenseD1(actor: string, id: string, action: string, days?: number) {
  const record = (await d1Database.query("SELECT * FROM licenses WHERE id=$1",[id])).rows[0];
  if (!record) throw new PublicError("not_found",404);
  const statements: Statement[] = [guard("EXISTS(SELECT 1 FROM licenses WHERE id=? AND generation=? AND status=? AND expires_at IS ?)",[id,record.generation,record.status,record.expires_at])];
  if (action === "lock") statements.push({sql:"UPDATE licenses SET status='locked',generation=generation+1 WHERE id=? AND status<>'revoked'",params:[id]});
  else if (action === "unlock") statements.push({sql:"UPDATE licenses SET status='active' WHERE id=? AND status='locked'",params:[id]});
  else if (action === "revoke") statements.push({sql:"UPDATE licenses SET status='revoked',generation=generation+1 WHERE id=?",params:[id]});
  else if (action === "extend") {
    if (record.plan_id === "trial") throw new PublicError("cannot_extend_trial");
    if (!days || days<1 || days>36500) throw new PublicError("invalid_days");
    if (!record.expires_at || record.status==="revoked") throw new PublicError("cannot_extend_lifetime_or_revoked");
    statements.push({sql:`UPDATE licenses SET expires_at=strftime('%Y-%m-%dT%H:%M:%fZ',max(expires_at,${nowSQL}),'+' || ? || ' days') WHERE id=?`,params:[days,id]});
  } else if (action === "reset") {
    if (record.status === "revoked") throw new PublicError("license_revoked");
    const key = newLicense();
    statements.push({sql:"DELETE FROM activations WHERE license_id=?",params:[id]},
      {sql:"UPDATE licenses SET key_hash=?,key_cipher=?,installation_key=NULL,generation=generation+1 WHERE id=?",params:[hash(key),encrypt(key),id]});
  } else throw new PublicError("invalid_action");
  statements.push({sql:"INSERT INTO audit_log(id,actor_id,action,target_id) VALUES(?,?,?,?)",params:[randomUUID(),actor,`license.${action}`,id]},clearGuard);
  await batch(statements);
}

export async function manualLicenseD1(actor: string, email: string, planId: string, requestId: string) {
  const key = newLicense(), id = randomUUID();
  await batch([
    guard("EXISTS(SELECT 1 FROM users WHERE email=?) AND EXISTS(SELECT 1 FROM plans WHERE id=?)",[email,planId]),
    {sql:`INSERT INTO licenses(id,user_id,plan_id,key_hash,key_cipher,manual_request_id,expires_at)
      SELECT ?,users.id,plans.id,?,?,?,CASE WHEN duration_days IS NULL THEN NULL ELSE ${afterSQL("'+' || duration_days || ' days'")} END
      FROM users CROSS JOIN plans WHERE users.email=? AND plans.id=? ON CONFLICT(manual_request_id) DO NOTHING`,params:[id,hash(key),encrypt(key),requestId,email,planId]},
    {sql:"INSERT INTO audit_log(id,actor_id,action,target_id) SELECT ?,?,'license.manual',? WHERE changes()>0",params:[randomUUID(),actor,id]},clearGuard,
  ]);
}
