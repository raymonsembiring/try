import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import logger from './logger.js';
import { PORT, JOBS_DIR } from './config.js';
import { getBaseUrl, buildOAuthRedirectUrl, buildTelegramWebhookUrl } from './utils/urls.js';
import { createAuthUrl, handleOAuthCallback } from './oauth/google.js';
import { bot, setupBotHandlers } from './telegram/bot.js';
import { runCreateShorts } from './workflow/runner.js';
import { getJob } from './db.js';

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

fs.mkdirSync(JOBS_DIR, { recursive: true });

// Static frontend
app.use('/', express.static(path.join('/workspace', 'web')));

// Health
app.get('/health', (_req, res) => res.json({ ok: true }));

// Utils endpoints providing URIs to paste in consoles
app.get('/utils/uris', (req, res) => {
  const base = getBaseUrl(req);
  res.json({
    base,
    telegramWebhook: buildTelegramWebhookUrl(base),
    googleOAuthRedirect: buildOAuthRedirectUrl(base)
  });
});

// Google OAuth begin
app.get('/oauth2/authorize', (req, res) => {
  const base = getBaseUrl(req);
  const telegramUserId = String(req.query.user_id || '');
  if (!telegramUserId) return res.status(400).send('Missing user_id');
  const { url } = createAuthUrl(base, telegramUserId);
  res.redirect(url);
});

// Google OAuth callback
app.get('/oauth2/callback', async (req, res) => {
  try {
    const base = getBaseUrl(req);
    const code = String(req.query.code || '');
    const state = String(req.query.state || '');
    await handleOAuthCallback(base, code, state);
    res.sendFile(path.join('/workspace', 'web', 'linked.html'));
  } catch (err) {
    logger.error({ err }, 'OAuth callback failed');
    res.status(400).send(String(err?.message || err));
  }
});

// Telegram webhook endpoint
app.post('/webhook/telegram', (req, res) => {
  bot.handleUpdate(req.body, res);
});

// Job status
app.get('/jobs/:id', (req, res) => {
  const job = getJob(req.params.id);
  if (!job) return res.status(404).json({ error: 'Not found' });
  res.json(job);
});

// Setup bot handlers wiring into workflow
setupBotHandlers(async ({ telegramUserId, url }) => {
  const base = 'http://localhost:' + PORT; // for internal workflow, real base is used in notify
  const jobId = await runCreateShorts({
    telegramUserId,
    url,
    baseUrl: base,
    notify: async (status) => {
      try { await bot.telegram.sendMessage(telegramUserId, `Status: ${status}`); } catch {}
    }
  });
  return jobId;
});

// Start server and setup webhook URL if provided
app.listen(PORT, async () => {
  logger.info({ PORT }, 'Server listening');
  try {
    const webhookInfo = await bot.telegram.getWebhookInfo();
    if (!webhookInfo || !webhookInfo.url) {
      logger.info('Telegram webhook not set. Use /utils/uris to configure.');
    }
  } catch (err) {
    logger.warn({ err }, 'Unable to read webhook info');
  }
});

export default app;

