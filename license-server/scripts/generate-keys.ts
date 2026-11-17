import { generateKeyPairSync, randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory=process.argv[2];
if(!directory)throw new Error("Usage: npm run keys:generate -- /private/directory-outside-repository");
const target=resolve(directory);
const repository=fileURLToPath(new URL("../../",import.meta.url));
const local=relative(repository,target);
if(!local.startsWith(".."))throw new Error("Use a private directory outside this repository");
await mkdir(target,{mode:0o700,recursive:true});
const pair=generateKeyPairSync("ed25519");
const pem=pair.privateKey.export({format:"pem",type:"pkcs8"}).toString();
const der=pair.publicKey.export({format:"der",type:"spki"});
await writeFile(`${target}/server-secrets.env`,[
  `AUTH_SECRET=${randomBytes(48).toString("base64")}`,
  `CRON_SECRET=${randomBytes(32).toString("base64")}`,
  `LICENSE_ENCRYPTION_KEY=${randomBytes(32).toString("base64")}`,
  `LICENSE_SIGNING_PRIVATE_KEY="${pem.trim().replace(/\n/g,"\\n")}"`,
].join("\n")+"\n",{mode:0o600,flag:"wx"});
await writeFile(`${target}/public-key.txt`,der.subarray(-32).toString("base64")+"\n",{mode:0o600,flag:"wx"});
console.log("Generated private environment file and public key. Do not commit the private file.");
