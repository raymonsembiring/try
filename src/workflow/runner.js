import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { JOBS_DIR } from '../config.js';
import { createJob, updateJobStatus } from '../db.js';
import { downloadVideo, trimAndFormat, extractAudio } from '../pipeline/video.js';
import { transcribeToSrt } from '../pipeline/transcriber.js';
import { getAuthorizedClient } from '../oauth/google.js';
import { uploadVideoWithCaptions } from '../pipeline/uploader.js';

export async function runCreateShorts({ telegramUserId, url, baseUrl, notify }) {
  const jobId = crypto.randomUUID();
  const jobDir = path.join(JOBS_DIR, jobId);
  fs.mkdirSync(jobDir, { recursive: true });
  createJob({ id: jobId, telegram_user_id: telegramUserId, source_url: url, status: 'queued' });

  const step = async (status, fn) => {
    updateJobStatus(jobId, status);
    if (notify) await notify(status);
    return fn();
  };

  try {
    const sourcePath = await step('downloading', async () => downloadVideo(url, jobDir));
    const shortsPath = await step('processing', async () => trimAndFormat(sourcePath, jobDir));
    const audioPath = await step('audio_extract', async () => extractAudio(shortsPath, jobDir));
    const srtPath = await step('transcribing', async () => transcribeToSrt(audioPath));

    const client = getAuthorizedClient(telegramUserId, baseUrl);
    if (!client) {
      throw new Error('Google not linked. Use the dashboard to connect your YouTube.');
    }

    const videoId = await step('uploading', async () => uploadVideoWithCaptions({
      oauth2Client: client,
      videoPath: shortsPath,
      srtPath,
      title: 'Shorts clip',
      description: 'Generated via bot',
      tags: ['shorts', 'bot']
    }));

    updateJobStatus(jobId, 'completed', { video_id: videoId });
    if (notify) await notify('completed');
  } catch (err) {
    updateJobStatus(jobId, 'failed', { error: String(err?.message || err) });
    if (notify) await notify(`failed: ${err?.message || err}`);
  }

  return jobId;
}

