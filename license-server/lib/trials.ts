import { randomUUID } from "node:crypto";
import { database, transaction } from "./db";
import { batch, clearGuard, d1Enabled, guard } from "./d1-client";
import { encrypt, hash, newLicense, PublicError } from "./security";

export async function claimTrial(userId: string) {
  const key=newLicense(), id=randomUUID();
  if (d1Enabled()) {
    const result=await batch([
      guard("EXISTS(SELECT 1 FROM trial_claims WHERE user_id=?) OR EXISTS(SELECT 1 FROM plans WHERE id='trial' AND active=1 AND amount=0 AND duration_days=1)",[userId]),
      {sql:"INSERT INTO licenses(id,user_id,plan_id,key_hash,key_cipher) SELECT ?,?,'trial',?,? WHERE NOT EXISTS(SELECT 1 FROM trial_claims WHERE user_id=?)",params:[id,userId,hash(key),encrypt(key),userId]},
      {sql:"INSERT INTO trial_claims(user_id,license_id) SELECT ?,? WHERE EXISTS(SELECT 1 FROM licenses WHERE id=?) ON CONFLICT(user_id) DO NOTHING",params:[userId,id,id]},
      {sql:"INSERT INTO audit_log(id,actor_id,action,target_id) SELECT ?,?,'license.trial',? WHERE EXISTS(SELECT 1 FROM licenses WHERE id=?)",params:[randomUUID(),userId,id,id]},
      {sql:"SELECT license_id FROM trial_claims WHERE user_id=?",params:[userId]},clearGuard,
    ]);
    return result[4].rows[0].license_id as string;
  }
  return transaction(async client=>{
    await client.query("SELECT id FROM users WHERE id=$1 FOR UPDATE",[userId]);
    const existing=(await client.query("SELECT license_id FROM trial_claims WHERE user_id=$1",[userId])).rows[0];
    if (existing) return existing.license_id as string;
    const plan=(await client.query("SELECT id FROM plans WHERE id='trial' AND active=true AND amount=0 AND duration_days=1")).rows[0];
    if (!plan) throw new PublicError("trial_unavailable",409);
    await client.query("INSERT INTO licenses(id,user_id,plan_id,key_hash,key_cipher) VALUES($1,$2,'trial',$3,$4)",[id,userId,hash(key),encrypt(key)]);
    await client.query("INSERT INTO trial_claims(user_id,license_id) VALUES($1,$2)",[userId,id]);
    await client.query("INSERT INTO audit_log(id,actor_id,action,target_id) VALUES($1,$2,'license.trial',$3)",[randomUUID(),userId,id]);
    return id;
  });
}
export async function trialWasClaimed(userId: string) {
  return !!(await database().query("SELECT user_id FROM trial_claims WHERE user_id=$1",[userId])).rows[0];
}
