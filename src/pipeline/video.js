import fs from 'node:fs';
import path from 'node:path';
import ffmpeg from 'fluent-ffmpeg';
import ffmpegStatic from 'ffmpeg-static';
import YTDlpWrap from 'yt-dlp-wrap';

ffmpeg.setFfmpegPath(ffmpegStatic);

const ytdlp = new YTDlpWrap();

export async function downloadVideo(url, outDir) {
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'source.mp4');
  await ytdlp.exec(['-o', outPath, url]);
  return outPath;
}

export function trimAndFormat(inputPath, outDir) {
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'shorts.mp4');
  return new Promise((resolve, reject) => {
    ffmpeg(inputPath)
      .setStartTime('0')
      .duration(58)
      .videoFilters([
        'scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih)',
        'crop=1080:1920'
      ])
      .outputOptions([
        '-c:v libx264',
        '-preset veryfast',
        '-crf 23',
        '-pix_fmt yuv420p',
        '-r 30',
        '-c:a aac',
        '-b:a 128k'
      ])
      .on('error', reject)
      .on('end', () => resolve(outPath))
      .save(outPath);
  });
}

export function extractAudio(inputPath, outDir) {
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'audio.m4a');
  return new Promise((resolve, reject) => {
    ffmpeg(inputPath)
      .noVideo()
      .audioCodec('aac')
      .audioBitrate('128k')
      .on('error', reject)
      .on('end', () => resolve(outPath))
      .save(outPath);
  });
}

