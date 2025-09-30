import { TELEGRAM_BOT_TOKEN } from '../config.js';
import { Telegraf } from 'telegraf';

if (!TELEGRAM_BOT_TOKEN) {
  throw new Error('TELEGRAM_BOT_TOKEN is required');
}

export const bot = new Telegraf(TELEGRAM_BOT_TOKEN);

export function setupBotHandlers(onCreateShorts) {
  bot.start((ctx) => ctx.reply('Send /create_shorts <YouTube_URL> to process.'));

  bot.command('create_shorts', async (ctx) => {
    const userId = ctx.from?.id;
    const text = ctx.message?.text || '';
    const parts = text.trim().split(/\s+/);
    const url = parts[1];
    if (!url) {
      await ctx.reply('Usage: /create_shorts <YouTube_URL>');
      return;
    }
    try {
      const jobId = await onCreateShorts({ telegramUserId: userId, url });
      await ctx.reply(`Processing started. Job: ${jobId}`);
    } catch (err) {
      await ctx.reply(`Failed: ${err.message}`);
    }
  });
}

