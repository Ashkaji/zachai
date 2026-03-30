/**
 * ZachAI Hocuspocus — Story 5.1 (Yjs + Redis ticket auth + Postgres persistence + Redis fan-out).
 */
import { Server } from "@hocuspocus/server";
import { Redis as HocuspocusRedis } from "@hocuspocus/extension-redis";
import { Redis } from "ioredis";
import pg from "pg";
import * as Y from "yjs";

const WSS_TICKET_PREFIX = "wss:ticket:";
const HOCUSPOCUS_REDIS_PREFIX = process.env.HOCUSPOCUS_REDIS_PREFIX ?? "hp:crdt:";

const PORT = parseInt(process.env.PORT ?? "1234", 10);
const HOST = process.env.HOST ?? "0.0.0.0";
const LOG_LEVEL = (process.env.LOG_LEVEL ?? "info").toLowerCase();

const REDIS_URL = (process.env.REDIS_URL ?? "").trim();
const DATABASE_URL = (process.env.DATABASE_URL ?? "").trim();

function log(level: string, msg: string, extra?: Record<string, unknown>) {
  const allowed = LOG_LEVEL === "debug" ? ["debug", "info", "warn", "error"] : ["info", "warn", "error"];
  if (!allowed.includes(level)) return;
  if (extra) {
    console.log(`[hocuspocus] ${msg}`, extra);
  } else {
    console.log(`[hocuspocus] ${msg}`);
  }
}

function requireEnv(): { redisUrl: string; databaseUrl: string } {
  if (!REDIS_URL) {
    throw new Error("REDIS_URL is required");
  }
  if (DATABASE_URL) {
    return { redisUrl: REDIS_URL, databaseUrl: DATABASE_URL };
  }
  const u = process.env.POSTGRES_USER ?? "";
  const p = process.env.POSTGRES_PASSWORD ?? "";
  const host = process.env.POSTGRES_HOST ?? "postgres";
  const port = process.env.POSTGRES_PORT ?? "5432";
  const db = process.env.POSTGRES_DB ?? "zachai";
  if (!u || !p) {
    throw new Error("DATABASE_URL or POSTGRES_USER and POSTGRES_PASSWORD are required");
  }
  const enc = encodeURIComponent(u);
  const encp = encodeURIComponent(p);
  return {
    redisUrl: REDIS_URL,
    databaseUrl: `postgres://${enc}:${encp}@${host}:${port}/${db}`,
  };
}

type TicketPayload = {
  sub: string;
  document_id: number;
  permissions: string[];
};

async function consumeTicket(redisClient: Redis, ticketId: string): Promise<TicketPayload | null> {
  const key = `${WSS_TICKET_PREFIX}${ticketId}`;
  const raw = await redisClient.getdel(key);
  if (raw == null) return null;
  try {
    return JSON.parse(raw) as TicketPayload;
  } catch {
    return null;
  }
}

const { redisUrl, databaseUrl } = requireEnv();

const pool = new pg.Pool({
  connectionString: databaseUrl,
  max: 20,
});

/** ioredis for WSS ticket GETDEL (same keyspace as FastAPI). */
const redisTicket = new Redis(redisUrl);
/** Dedicated client for @hocuspocus/extension-redis (pub/sub + distinct prefix). */
const redisCollab = new Redis(redisUrl);

async function loadDocumentState(documentId: number, document: Y.Doc): Promise<void> {
  const client = await pool.connect();
  try {
    const res = await client.query<{ update_binary: Buffer }>(
      `SELECT update_binary FROM yjs_logs WHERE document_id = $1 ORDER BY id DESC LIMIT 1`,
      [documentId],
    );
    const row = res.rows[0];
    if (row?.update_binary?.length) {
      Y.applyUpdate(document, new Uint8Array(row.update_binary));
    }
  } finally {
    client.release();
  }
}

async function storeDocumentState(documentId: number, document: Y.Doc): Promise<void> {
  const update = Y.encodeStateAsUpdate(document);
  if (update.byteLength === 0) return;
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(`DELETE FROM yjs_logs WHERE document_id = $1`, [documentId]);
    await client.query(
      `INSERT INTO yjs_logs (document_id, update_binary) VALUES ($1, $2)`,
      [documentId, Buffer.from(update)],
    );
    await client.query("COMMIT");
  } catch (e) {
    try {
      await client.query("ROLLBACK");
    } catch {
      /* ignore */
    }
    throw e;
  } finally {
    client.release();
  }
}

const server = Server.configure({
  port: PORT,
  address: HOST,
  quiet: true,
  extensions: [
    new HocuspocusRedis({
      redis: redisCollab,
      prefix: HOCUSPOCUS_REDIS_PREFIX,
      identifier: process.env.HOCUSPOCUS_INSTANCE_ID ?? `hp-${process.pid}`,
    }),
  ],

  async onAuthenticate(data) {
    const ticketId = (data.token ?? "").trim();
    if (!ticketId) {
      throw new Error("Missing ticket");
    }

    const documentName = data.documentName ?? "";
    const documentId = parseInt(documentName, 10);
    if (Number.isNaN(documentId) || documentId < 1) {
      throw new Error("Invalid document id");
    }

    const payload = await consumeTicket(redisTicket, ticketId);
    if (!payload) {
      throw new Error("Invalid or expired ticket");
    }

    if (payload.document_id !== documentId) {
      throw new Error("Ticket does not match document");
    }

    const perms = Array.isArray(payload.permissions) ? payload.permissions : [];
    const canWrite = perms.includes("write");
    if (!canWrite) {
      data.connection.readOnly = true;
    }

    log("info", "authenticated", {
      document_id: documentId,
      sub: payload.sub,
      readOnly: !canWrite,
    });

    return {
      user: {
        id: payload.sub,
        name: payload.sub,
      },
    };
  },

  async onLoadDocument({ documentName, document }) {
    const documentId = parseInt(documentName, 10);
    if (Number.isNaN(documentId)) return;
    await loadDocumentState(documentId, document);
  },

  async onStoreDocument({ documentName, document }) {
    const documentId = parseInt(documentName, 10);
    if (Number.isNaN(documentId)) return;
    await storeDocumentState(documentId, document);
  },
});

void server.listen();

log("info", `listening on ws://${HOST}:${PORT} (document name = audio_files.id)`);
log("info", `Redis collab prefix: ${HOCUSPOCUS_REDIS_PREFIX}`);

function shutdown() {
  log("info", "shutting down");
  void server.destroy();
  void redisTicket.quit();
  void redisCollab.quit();
  void pool.end();
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
