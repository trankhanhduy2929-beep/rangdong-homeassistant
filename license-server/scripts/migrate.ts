import { readFile } from "node:fs/promises";
import { database } from "../lib/db";

await database().query(await readFile(new URL("../db/001.sql", import.meta.url),"utf8"));
await database().query(await readFile(new URL("../db/002.sql", import.meta.url),"utf8"));
await database().end();
console.log("Database migration completed");
