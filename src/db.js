import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';

const DATA_DIR = path.resolve('/workspace/data');
const DB_PATH = path.join(DATA_DIR, 'app.db');

if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

const db = new Database(DB_PATH);

db.pragma('journal_mode = WAL');

db.exec(`
CREATE TABLE IF NOT EXISTS oauth_tokens (
  telegram_user_id TEXT PRIMARY KEY,
  access_token TEXT,
  refresh_token TEXT,
  scope TEXT,
  token_type TEXT,
  expiry_date INTEGER
);

CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  telegram_user_id TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  telegram_user_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  video_id TEXT,
  error TEXT
);
`);

export function upsertToken(telegramUserId, token) {
  const stmt = db.prepare(`
    INSERT INTO oauth_tokens (telegram_user_id, access_token, refresh_token, scope, token_type, expiry_date)
    VALUES (@telegram_user_id, @access_token, @refresh_token, @scope, @token_type, @expiry_date)
    ON CONFLICT(telegram_user_id) DO UPDATE SET
      access_token=excluded.access_token,
      refresh_token=COALESCE(excluded.refresh_token, oauth_tokens.refresh_token),
      scope=excluded.scope,
      token_type=excluded.token_type,
      expiry_date=excluded.expiry_date
  `);
  stmt.run({
    telegram_user_id: String(telegramUserId),
    access_token: token.access_token,
    refresh_token: token.refresh_token || null,
    scope: token.scope || null,
    token_type: token.token_type || 'Bearer',
    expiry_date: token.expiry_date || null
  });
}

export function getToken(telegramUserId) {
  const row = db.prepare('SELECT * FROM oauth_tokens WHERE telegram_user_id = ?').get(String(telegramUserId));
  return row || null;
}

export function deleteToken(telegramUserId) {
  db.prepare('DELETE FROM oauth_tokens WHERE telegram_user_id = ?').run(String(telegramUserId));
}

export function createState(telegramUserId, state) {
  db.prepare('INSERT INTO oauth_states (state, telegram_user_id, created_at) VALUES (?, ?, ?)')
    .run(state, String(telegramUserId), Date.now());
}

export function consumeState(state) {
  const row = db.prepare('SELECT * FROM oauth_states WHERE state = ?').get(state);
  if (row) {
    db.prepare('DELETE FROM oauth_states WHERE state = ?').run(state);
  }
  return row || null;
}

export function createJob(job) {
  const now = Date.now();
  db.prepare(`
    INSERT INTO jobs (id, telegram_user_id, source_url, status, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(job.id, String(job.telegram_user_id), job.source_url, job.status, now, now);
}

export function updateJobStatus(id, status, extra = {}) {
  const now = Date.now();
  const { video_id = null, error = null } = extra;
  db.prepare(`
    UPDATE jobs SET status = ?, updated_at = ?, video_id = COALESCE(?, video_id), error = ? WHERE id = ?
  `).run(status, now, video_id, error, id);
}

export function getJob(id) {
  return db.prepare('SELECT * FROM jobs WHERE id = ?').get(id);
}

export default db;

