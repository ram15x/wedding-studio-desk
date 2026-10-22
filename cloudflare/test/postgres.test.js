import test from "node:test";
import assert from "node:assert/strict";
import { PostgresD1Compat, postgresSql } from "../src/postgres.js";

test("Postgres SQL maps app tables and SQLite placeholders", () => {
  assert.equal(
    postgresSql("SELECT * FROM wedding_guests WHERE phone=? AND id=?"),
    "SELECT * FROM ishqweds_guests WHERE phone=$1 AND id=$2",
  );
  assert.equal(postgresSql("SELECT COUNT(*) count FROM wedding_guests"), "SELECT COUNT(*)::int AS count FROM ishqweds_guests");
});

test("compatibility adapter binds values and returns D1-shaped results", async () => {
  const calls = [];
  const client = { query: async (sql, params=[]) => {
    calls.push([sql, params]);
    return { rows: [{ id: 42, name: "Synthetic guest" }], rowCount: 1 };
  }};
  const db = new PostgresD1Compat(client);
  const row = await db.prepare("SELECT * FROM wedding_guests WHERE phone=?").bind("0000000000").first();
  assert.equal(row.name, "Synthetic guest");
  assert.deepEqual(calls[0], ["SELECT * FROM ishqweds_guests WHERE phone=$1", ["0000000000"]]);
  const result = await db.prepare("UPDATE wedding_guests SET name=? WHERE id=?").bind("Guest",42).run();
  assert.equal(result.meta.changes, 1);
});

test("batch commits all queries together and rolls back on failure", async () => {
  const calls = [];
  let fail = false;
  const client = { query: async (sql, params=[]) => {
    calls.push(sql);
    if (fail && sql.startsWith("INSERT")) throw new Error("expected failure");
    return { rows: [], rowCount: 1 };
  }};
  const db = new PostgresD1Compat(client);
  await db.batch([
    db.prepare("DELETE FROM guest_messages"),
    db.prepare("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES(?,?,?)").bind("k","v","now"),
  ]);
  assert.deepEqual(calls.slice(0,4), ["BEGIN","DELETE FROM ishqweds_messages","INSERT INTO ishqweds_facts(fact_key,fact_value,updated_at) VALUES($1,$2,$3)","COMMIT"]);
  calls.length=0; fail=true;
  await assert.rejects(db.batch([db.prepare("INSERT INTO wedding_facts(fact_key,fact_value,updated_at) VALUES(?,?,?)").bind("k","v","now")]), /expected failure/);
  assert.deepEqual(calls, ["BEGIN","INSERT INTO ishqweds_facts(fact_key,fact_value,updated_at) VALUES($1,$2,$3)","ROLLBACK"]);
});
