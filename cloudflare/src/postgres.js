import { Client } from "pg";

const TABLE_MAP = [
  ["wedding_guests", "ishqweds_guests"],
  ["wedding_facts", "ishqweds_facts"],
  ["guest_sessions", "ishqweds_sessions"],
  ["guest_messages", "ishqweds_messages"],
  ["family_inbox", "ishqweds_family_inbox"],
];

export function postgresSql(sql) {
  let parameter = 0;
  let converted = sql.replace(/\?/g, () => `$${++parameter}`);
  for (const [source, target] of TABLE_MAP)
    converted = converted.replace(new RegExp(`\\b${source}\\b`, "g"), target);
  converted = converted.replace(/COUNT\(\*\)\s+count/i, "COUNT(*)::int AS count");
  return converted;
}

export class PostgresD1Compat {
  constructor(client) { this.client = client; }

  prepare(sql) {
    const statement = postgresSql(sql);
    return {
      bind: (...params) => ({
        first: async () => (await this.client.query(statement, params)).rows[0] || null,
        all: async () => ({ results: (await this.client.query(statement, params)).rows }),
        run: async () => {
          const result = await this.client.query(statement, params);
          return { success: true, meta: { changes: result.rowCount || 0 } };
        },
        query: statement,
        params,
      }),
      first: async () => (await this.client.query(statement)).rows[0] || null,
      all: async () => ({ results: (await this.client.query(statement)).rows }),
      run: async () => {
        const result = await this.client.query(statement);
        return { success: true, meta: { changes: result.rowCount || 0 } };
      },
      query: statement,
      params: [],
    };
  }

  async batch(statements) {
    await this.client.query("BEGIN");
    try {
      const results = [];
      for (const statement of statements) {
        const result = await this.client.query(statement.query, statement.params || []);
        results.push({ success: true, meta: { changes: result.rowCount || 0 } });
      }
      await this.client.query("COMMIT");
      return results;
    } catch (error) {
      await this.client.query("ROLLBACK");
      throw error;
    }
  }
}

export async function connectPostgres(connectionString) {
  if (!connectionString) throw new Error("Supabase PostgreSQL Hyperdrive binding is missing.");
  const client = new Client({ connectionString });
  await client.connect();
  return { db: new PostgresD1Compat(client), close: () => client.end() };
}
