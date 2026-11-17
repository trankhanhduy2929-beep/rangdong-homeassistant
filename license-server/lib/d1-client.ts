import { PublicError, required } from "./security";

export type Statement = { sql: string; params?: unknown[] };
export type Row = Record<string, any>;
export const d1Enabled = () => process.env.DATABASE_PROVIDER === "d1";
export const nowSQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')";
export const afterSQL = (modifier: string) => `strftime('%Y-%m-%dT%H:%M:%fZ','now',${modifier})`;

export async function batch(statements: Statement[]): Promise<{ rows: Row[] }[]> {
  const url = new URL(required("D1_GATEWAY_URL"));
  if (url.protocol !== "https:") throw new Error("D1 gateway requires HTTPS");
  const response = await fetch(url, { method: "POST", cache: "no-store", signal: AbortSignal.timeout(20000),
    headers: { Authorization: `Bearer ${required("D1_GATEWAY_SECRET")}`, "Content-Type": "application/json" },
    body: JSON.stringify({ statements }) });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (payload.error === "transaction_conflict") throw new PublicError("transaction_conflict", 409);
    throw new Error("D1 unavailable");
  }
  return (await response.json()).results;
}

export function translate(sql: string, params: unknown[] = []): Statement {
  if (/FOR UPDATE|\bBEGIN\b|\bCOMMIT\b|\bROLLBACK\b/i.test(sql)) throw new Error("Use atomic D1 operations");
  let converted = sql.replace(/now\(\)\s*([+-])\s*\$(\d+)\s*\*\s*interval '1 (second|day)'/gi,
    (_, sign, index, unit) => afterSQL(`'${sign}' || $${index} || ' ${unit}s'`));
  converted = converted.replace(/now\(\)\s*([+-])\s*interval '(\d+) (minutes?|hours?|days?)'/gi,
    (_, sign, count, unit) => afterSQL(`'${sign}${count} ${unit}'`)).replace(/now\(\)/gi, nowSQL);
  const values: unknown[] = [];
  converted = converted.replace(/\$(\d+)/g, (_, index) => { values.push(params[Number(index)-1] ?? null); return "?"; });
  return { sql: converted, params: values };
}

export const d1Database = { async query(sql: string, params?: unknown[]) {
  return (await batch([translate(sql, params)]))[0];
} };

export function guard(condition: string, params: unknown[] = []): Statement {
  return { sql: `INSERT INTO transaction_guard(value) VALUES(CASE WHEN (${condition}) THEN 1 ELSE 0 END)`, params };
}
export const clearGuard: Statement = { sql: "DELETE FROM transaction_guard" };
