import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";

async function derive(password: string, salt: Buffer): Promise<Buffer> {
  return new Promise((resolve,reject) => scrypt(password,salt,64,{N:32768,r:8,p:3,maxmem:64*1024*1024},(error,key)=>error?reject(error):resolve(key)));
}
export async function passwordHash(password: string) {
  const salt=randomBytes(16);
  return `scrypt-v1:${salt.toString("hex")}:${(await derive(password,salt)).toString("hex")}`;
}
export async function passwordMatches(password: string, encoded?: string) {
  const valid=encoded?.match(/^scrypt-v1:([a-f0-9]{32}):([a-f0-9]{128})$/);
  const actual=await derive(password,valid?Buffer.from(valid[1],"hex"):Buffer.alloc(16));
  return !!valid && timingSafeEqual(actual,Buffer.from(valid[2],"hex"));
}
