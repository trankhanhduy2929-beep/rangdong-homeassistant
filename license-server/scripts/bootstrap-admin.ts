import { randomBytes, randomUUID } from "node:crypto";
import { open, mkdir } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { database, transaction } from "../lib/db";
import { batch, d1Enabled } from "../lib/d1-client";
import { isAdmin } from "../lib/auth";
import { passwordHash } from "../lib/passwords";

const email=process.argv[2]?.trim().toLowerCase(), output=process.argv[3];
if (!email || !output || !isAdmin(email)) throw new Error("Usage: bootstrap-admin.ts ADMIN_EMAIL /private/path-outside-repo.txt");
const target=resolve(output), repository=fileURLToPath(new URL("../../",import.meta.url));
if (!relative(repository,target).startsWith("..")) throw new Error("Output must be outside repository");
if ((await database().query("SELECT id FROM users WHERE email=$1",[email])).rows[0]) throw new Error("Account exists; no overwrite or automatic promotion allowed");
const password=randomBytes(24).toString("base64url"), encoded=await passwordHash(password), userId=randomUUID();
await mkdir(dirname(target),{recursive:true,mode:0o700});
const file=await open(target,"wx",0o600);
try {await file.writeFile(`EMAIL=${email}\nPASSWORD=${password}\n`);} finally {await file.close();}
if (d1Enabled()) await batch([
  {sql:"INSERT INTO users(id,email) VALUES(?,?)",params:[userId,email]},
  {sql:"INSERT INTO auth_credentials(user_id,password_hash) VALUES(?,?)",params:[userId,encoded]},
  {sql:"INSERT INTO administrator_accounts(user_id) VALUES(?)",params:[userId]},
]);
else {
  await transaction(async client=>{
    await client.query("INSERT INTO users(id,email) VALUES($1,$2)",[userId,email]);
    await client.query("INSERT INTO auth_credentials(user_id,password_hash) VALUES($1,$2)",[userId,encoded]);
    await client.query("INSERT INTO administrator_accounts(user_id) VALUES($1)",[userId]);
  });
  await database().end();
}
console.log("Admin created. Credentials saved privately; values not printed.");
