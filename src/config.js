import 'dotenv/config';

export const PORT = Number(process.env.PORT || 8080);
export const PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || '';

export const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';

export const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID || '';
export const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || '';

export const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';

export const JOBS_DIR = process.env.JOBS_DIR || '/workspace/jobs';

