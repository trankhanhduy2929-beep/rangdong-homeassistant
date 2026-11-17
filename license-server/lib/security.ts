import { createHash, createHmac, randomBytes, createCipheriv, createDecipheriv,
  sign, verify, createPublicKey, timingSafeEqual } from "node:crypto";

export class PublicError extends Error {
  constructor(public code: string, public status = 400) { super(code); }
}
export function required(name: string) {
  const value = process.env[name];
  if (!value) throw new Error(`${name} missing`);
  return value;
}
export function origin() { return new URL(required("APP_URL")).origin; }
export function hash(value: string) { return createHash("sha256").update(value).digest("hex"); }
export function digestCode(email: string, code: string) {
  return createHmac("sha256", required("AUTH_SECRET")).update(`${email}:${code}`).digest("hex");
}
export function equals(left: string, right: string) {
  const first = Buffer.from(left); const second = Buffer.from(right);
  return first.length === second.length && timingSafeEqual(first, second);
}
function cipherKey() {
  const key = Buffer.from(required("LICENSE_ENCRYPTION_KEY"), "base64");
  if (key.length !== 32) throw new Error("Invalid encryption key");
  return key;
}
export function encrypt(value: string) {
  const nonce = randomBytes(12); const cipher = createCipheriv("aes-256-gcm", cipherKey(), nonce);
  cipher.setAAD(Buffer.from("rangdong-license-v1"));
  const payload = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return Buffer.concat([nonce, cipher.getAuthTag(), payload]).toString("base64url");
}
export function decrypt(value: string) {
  const buffer = Buffer.from(value, "base64url");
  const cipher = createDecipheriv("aes-256-gcm", cipherKey(), buffer.subarray(0, 12));
  cipher.setAAD(Buffer.from("rangdong-license-v1")); cipher.setAuthTag(buffer.subarray(12, 28));
  return Buffer.concat([cipher.update(buffer.subarray(28)), cipher.final()]).toString("utf8");
}
export function newLicense() { return `RD-${randomBytes(24).toString("hex").toUpperCase()}`; }
export function verifyInstallation(raw: string, signature: string, publicKey: string) {
  try {
    const decoded = Buffer.from(publicKey, "base64");
    if (decoded.length !== 32) return false;
    const key = createPublicKey({ key: Buffer.concat([Buffer.from("302a300506032b6570032100", "hex"), decoded]), format: "der", type: "spki" });
    return verify(null, Buffer.from(raw), key, Buffer.from(signature, "base64"));
  } catch { return false; }
}
export function lease(payload: Record<string, unknown>) {
  const encoded = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = sign(null, Buffer.from(encoded), required("LICENSE_SIGNING_PRIVATE_KEY").replace(/\\n/g, "\n"));
  return `${encoded}.${signature.toString("base64url")}`;
}
