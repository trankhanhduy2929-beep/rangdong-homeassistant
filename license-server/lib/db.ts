import { Pool, PoolClient } from "pg";
import { batch, d1Database, d1Enabled, translate, type Statement } from "./d1-client";

let pool: Pool | undefined;
export async function readQueries(statements: Statement[]) {
  if (d1Enabled()) return batch(statements.map(item=>translate(item.sql,item.params)));
  return Promise.all(statements.map(item=>database().query(item.sql,item.params)));
}
export function database() {
  if (d1Enabled()) return d1Database as unknown as Pool;
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL missing");
  pool ??= new Pool({ connectionString: process.env.DATABASE_URL, max: 3, connectionTimeoutMillis: 10000,
    idleTimeoutMillis: 10000, statement_timeout: 15000 });
  return pool;
}
export async function transaction<Result>(work: (client: PoolClient) => Promise<Result>) {
  if (d1Enabled()) throw new Error("D1 requires atomic batch operations");
  const client = await database().connect();
  try {
    await client.query("BEGIN");
    const result = await work(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally { client.release(); }
}
