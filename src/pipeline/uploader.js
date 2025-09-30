import fs from 'node:fs';
import { google } from 'googleapis';

export async function uploadVideoWithCaptions({ oauth2Client, videoPath, srtPath, title, description, tags = [] }) {
  const youtube = google.youtube({ version: 'v3', auth: oauth2Client });

  const insertResponse = await youtube.videos.insert({
    part: ['snippet', 'status'],
    requestBody: {
      snippet: { title, description, tags, categoryId: '22' },
      status: { privacyStatus: 'private', selfDeclaredMadeForKids: false }
    },
    media: { body: fs.createReadStream(videoPath) }
  });

  const videoId = insertResponse.data.id;

  if (srtPath && fs.existsSync(srtPath)) {
    await youtube.captions.insert({
      part: ['snippet'],
      requestBody: {
        snippet: {
          videoId,
          language: 'en',
          name: 'Auto-generated',
          isDraft: false
        }
      },
      media: { body: fs.createReadStream(srtPath) }
    });
  }

  return videoId;
}

