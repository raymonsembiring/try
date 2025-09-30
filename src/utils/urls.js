import { PUBLIC_BASE_URL, PORT } from '../config.js';

export function getBaseUrl(req) {
  if (PUBLIC_BASE_URL) return PUBLIC_BASE_URL.replace(/\/$/, '');
  const proto = req.headers['x-forwarded-proto'] || req.protocol || 'http';
  const host = req.headers['x-forwarded-host'] || req.headers.host || `localhost:${PORT}`;
  return `${proto}://${host}`;
}

export function buildTelegramWebhookUrl(base) {
  return `${base}/webhook/telegram`;
}

export function buildOAuthRedirectUrl(base) {
  return `${base}/oauth2/callback`;
}

