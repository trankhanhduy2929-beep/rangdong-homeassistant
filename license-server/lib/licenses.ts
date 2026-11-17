import { randomUUID } from "node:crypto";
import type { PoolClient } from "pg";
import { z } from "zod";
import { database, transaction } from "./db";
import { encrypt, hash, lease, newLicense, PublicError, verifyInstallation } from "./security";
import { d1Enabled } from "./d1-client";
import { activateD1, adminLicenseD1, manualLicenseD1 } from "./d1-operations";
import { claimTrial } from "./trials";

export const activationSchema = z.object({
  key: z.string().regex(/^RD-[A-F0-9]{48}$/), installation: z.string().length(44),
  client_id: z.uuid(), component: z.enum(["addon", "custom"]),
  timestamp: z.number().int(), nonce: z.uuid(), signature: z.string().max(128),
});
export type Activation = z.infer<typeof activationSchema>;
export function requestMessage(data: Omit<Activation,"signature">) {
  return ["rangdong-license-v1", data.key, data.installation, data.client_id,
    data.component, data.timestamp, data.nonce].join("\n");
}
export async function bindLicense(client: PoolClient, data: Activation) {
  const record = (await client.query("SELECT * FROM licenses WHERE key_hash=$1 FOR UPDATE", [hash(data.key)])).rows[0];
  if (!record || record.status !== "active" || (record.expires_at && new Date(record.expires_at).getTime() <= Date.now())) {
    throw new PublicError("license_invalid", 403);
  }
  if (record.installation_key && record.installation_key !== data.installation) throw new PublicError("license_bound", 409);
  const slot = (await client.query("SELECT client_id FROM activations WHERE license_id=$1 AND component=$2", [record.id, data.component])).rows[0];
  if (slot && slot.client_id !== data.client_id) throw new PublicError("component_bound", 409);
  if (record.plan_id === "trial") {
    const previous=(await client.query("SELECT installation_key,license_id FROM trial_installations WHERE installation_key=$1 OR license_id=$2",[data.installation,record.id])).rows;
    if (previous.some(item=>item.license_id!==record.id || item.installation_key!==data.installation)) throw new PublicError("trial_already_used",409);
    await client.query("INSERT INTO trial_installations(installation_key,license_id) VALUES($1,$2) ON CONFLICT DO NOTHING",[data.installation,record.id]);
    const bound=(await client.query("SELECT license_id FROM trial_installations WHERE installation_key=$1",[data.installation])).rows[0];
    if (bound?.license_id!==record.id) throw new PublicError("trial_already_used",409);
    record.expires_at=(await client.query("UPDATE licenses SET expires_at=coalesce(expires_at,now()+interval '1 day') WHERE id=$1 RETURNING expires_at",[record.id])).rows[0].expires_at;
  }
  await client.query("UPDATE licenses SET installation_key=$1 WHERE id=$2", [data.installation, record.id]);
  await client.query(`INSERT INTO activations(license_id,component,client_id) VALUES($1,$2,$3)
    ON CONFLICT(license_id,component) DO UPDATE SET last_seen=now()`, [record.id, data.component, data.client_id]);
  const now = Math.floor(Date.now()/1000);
  return lease({ v: 1, license_id: record.id, installation: data.installation, client_id: data.client_id,
    component: data.component, generation: record.generation, iat: now,
    exp: Math.min(now + 72*3600, record.expires_at ? Math.floor(new Date(record.expires_at).getTime()/1000) : now + 72*3600) });
}
export async function activateLicense(data: Activation) {
  if (Math.abs(Date.now()/1000 - data.timestamp) > 300 || !verifyInstallation(requestMessage(data), data.signature, data.installation)) {
    throw new PublicError("invalid_proof", 401);
  }
  if (d1Enabled()) return activateD1(data);
  return transaction(async client => {
    await client.query("DELETE FROM license_nonces WHERE expires_at<now()");
    const nonce = await client.query("INSERT INTO license_nonces VALUES($1,now()+interval '10 minutes') ON CONFLICT DO NOTHING RETURNING digest", [hash(`${data.installation}:${data.nonce}`)]);
    if (!nonce.rows[0]) throw new PublicError("replayed_request", 409);
    return bindLicense(client, data);
  });
}
export async function adminLicense(actor: string, id: string, action: string, days?: number) {
  if (d1Enabled()) return adminLicenseD1(actor,id,action,days);
  await transaction(async client => {
    const record = (await client.query("SELECT * FROM licenses WHERE id=$1 FOR UPDATE", [id])).rows[0];
    if (!record) throw new PublicError("not_found", 404);
    if (action === "lock") await client.query("UPDATE licenses SET status='locked',generation=generation+1 WHERE id=$1 AND status<>'revoked'", [id]);
    else if (action === "unlock") await client.query("UPDATE licenses SET status='active' WHERE id=$1 AND status='locked'", [id]);
    else if (action === "revoke") await client.query("UPDATE licenses SET status='revoked',generation=generation+1 WHERE id=$1", [id]);
    else if (action === "extend") {
      if (record.plan_id === "trial") throw new PublicError("cannot_extend_trial");
      if (!days || days < 1 || days > 36500) throw new PublicError("invalid_days");
      if (!record.expires_at || record.status === "revoked") throw new PublicError("cannot_extend_lifetime_or_revoked");
      await client.query("UPDATE licenses SET expires_at=greatest(expires_at,now())+$2*interval '1 day' WHERE id=$1", [id, days]);
    } else if (action === "reset") {
      if (record.status === "revoked") throw new PublicError("license_revoked");
      const key = newLicense();
      await client.query("DELETE FROM activations WHERE license_id=$1", [id]);
      await client.query("UPDATE licenses SET key_hash=$2,key_cipher=$3,installation_key=NULL,generation=generation+1 WHERE id=$1", [id, hash(key), encrypt(key)]);
    } else throw new PublicError("invalid_action");
    await client.query("INSERT INTO audit_log(id,actor_id,action,target_id) VALUES($1,$2,$3,$4)", [randomUUID(), actor, `license.${action}`, id]);
  });
}
export async function manualLicense(actor: string, email: string, planId: string, requestId: string) {
  if (planId === "trial") {
    const user=(await database().query("SELECT id FROM users WHERE email=$1",[email])).rows[0];
    if (!user) throw new PublicError("user_or_plan_not_found");
    await claimTrial(user.id); return;
  }
  if (d1Enabled()) return manualLicenseD1(actor,email,planId,requestId);
  await transaction(async client => {
    const user = (await client.query("SELECT id FROM users WHERE email=$1", [email])).rows[0];
    const plan = (await client.query("SELECT * FROM plans WHERE id=$1", [planId])).rows[0];
    if (!user || !plan) throw new PublicError("user_or_plan_not_found");
    const key = newLicense();
    const inserted = await client.query(`INSERT INTO licenses(id,user_id,plan_id,key_hash,key_cipher,manual_request_id,expires_at)
      VALUES($1,$2,$3,$4,$5,$6,CASE WHEN $7::integer IS NULL THEN NULL ELSE now()+$7*interval '1 day' END)
      ON CONFLICT(manual_request_id) DO NOTHING RETURNING id`, [randomUUID(), user.id, plan.id, hash(key), encrypt(key), requestId, plan.duration_days]);
    if (inserted.rows[0]) await client.query("INSERT INTO audit_log(id,actor_id,action,target_id) VALUES($1,$2,'license.manual',$3)", [randomUUID(), actor, inserted.rows[0].id]);
  });
}
