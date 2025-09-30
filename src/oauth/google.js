import crypto from 'node:crypto';
import { google } from 'googleapis';
import { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET } from '../config.js';
import { buildOAuthRedirectUrl } from '../utils/urls.js';
import { createState, consumeState, getToken, upsertToken } from '../db.js';

const SCOPES = [
  'https://www.googleapis.com/auth/youtube.upload',
  'https://www.googleapis.com/auth/youtube.force-ssl'
];

export function createAuthUrl(baseUrl, telegramUserId) {
  const redirectUri = buildOAuthRedirectUrl(baseUrl);
  const state = crypto.randomBytes(16).toString('hex');
  createState(telegramUserId, state);

  const client = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, redirectUri);
  const url = client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
    prompt: 'consent',
    state
  });
  return { url, state, redirectUri };
}

export async function handleOAuthCallback(baseUrl, code, state) {
  const stateRow = consumeState(state);
  if (!stateRow) throw new Error('Invalid or expired state');
  const { telegram_user_id } = stateRow;

  const redirectUri = buildOAuthRedirectUrl(baseUrl);
  const client = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, redirectUri);

  const { tokens } = await client.getToken(code);
  if (!tokens) throw new Error('No tokens received');
  upsertToken(telegram_user_id, tokens);
  return { telegramUserId: telegram_user_id };
}

export function getAuthorizedClient(telegramUserId, baseUrl) {
  const redirectUri = buildOAuthRedirectUrl(baseUrl);
  const client = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, redirectUri);
  const token = getToken(telegramUserId);
  if (!token) return null;
  client.setCredentials({
    access_token: token.access_token,
    refresh_token: token.refresh_token,
    scope: token.scope,
    token_type: token.token_type,
    expiry_date: token.expiry_date
  });
  return client;
}

