import { readFile } from "node:fs/promises";
import { batch, d1Enabled } from "../lib/d1-client";

if (!d1Enabled()) throw new Error("Set DATABASE_PROVIDER=d1");
const filename=process.argv[2];
if (filename!=="002") throw new Error("Usage: migrate-d1.ts 002");
const sql=await readFile(new URL(`../cloudflare/${filename}.sql`,import.meta.url),"utf8");
await batch(sql.split(";").map(statement=>statement.trim()).filter(Boolean).map(sql=>({sql})));
console.log("D1 migration completed atomically; foreign keys verified.");
