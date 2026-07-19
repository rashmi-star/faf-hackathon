import { NextResponse } from 'next/server';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { basename, join, resolve } from 'node:path';
import { Readable } from 'node:stream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const MEDIA_DIR = resolve(
  process.env.DIRECTOR_MEDIA_DIR ?? join(process.cwd(), '..', 'agent', 'media-cache')
);

export async function GET(_request: Request, context: { params: Promise<{ filename: string }> }) {
  const { filename } = await context.params;
  if (basename(filename) !== filename || !/^[a-z0-9-]+\.(wav|mp3|m4a)$/i.test(filename)) {
    return NextResponse.json({ error: 'Invalid media filename' }, { status: 400 });
  }

  const filePath = join(MEDIA_DIR, filename);
  try {
    const file = await stat(filePath);
    if (!file.isFile()) throw new Error('not a file');
    const contentType = filename.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg';
    return new Response(Readable.toWeb(createReadStream(filePath)) as ReadableStream, {
      headers: {
        'Content-Type': contentType,
        'Content-Length': String(file.size),
        'Cache-Control': 'private, no-store',
      },
    });
  } catch {
    return NextResponse.json({ error: 'Media not found' }, { status: 404 });
  }
}
