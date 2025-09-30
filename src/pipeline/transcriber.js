import OpenAI from 'openai';
import fs from 'node:fs';
import path from 'node:path';
import { OPENAI_API_KEY } from '../config.js';

const client = new OpenAI({ apiKey: OPENAI_API_KEY });

export async function transcribeToSrt(audioPath, langHint = 'en') {
  const file = fs.createReadStream(audioPath);
  const response = await client.audio.transcriptions.create({
    file,
    model: 'gpt-4o-transcribe',
    language: langHint,
    response_format: 'verbose_json'
  });

  const srt = segmentsToSrt(response.segments || []);
  const srtPath = path.join(path.dirname(audioPath), 'subtitles.srt');
  fs.writeFileSync(srtPath, srt, 'utf8');
  return srtPath;
}

function toTimestamp(seconds) {
  const ms = Math.max(0, Math.floor(seconds * 1000));
  const hh = String(Math.floor(ms / 3600000)).padStart(2, '0');
  const mm = String(Math.floor((ms % 3600000) / 60000)).padStart(2, '0');
  const ss = String(Math.floor((ms % 60000) / 1000)).padStart(2, '0');
  const mmm = String(ms % 1000).padStart(3, '0');
  return `${hh}:${mm}:${ss},${mmm}`;
}

function segmentsToSrt(segments) {
  let idx = 1;
  const lines = [];
  for (const seg of segments) {
    if (typeof seg?.start !== 'number' || typeof seg?.end !== 'number') continue;
    const text = (seg?.text || '').trim();
    if (!text) continue;
    lines.push(String(idx++));
    lines.push(`${toTimestamp(seg.start)} --> ${toTimestamp(seg.end)}`);
    lines.push(text);
    lines.push('');
  }
  return lines.join('\n');
}

