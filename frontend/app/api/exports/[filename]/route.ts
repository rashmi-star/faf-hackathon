import { NextResponse } from 'next/server';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { basename, join, resolve } from 'node:path';
import { Readable } from 'node:stream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const EXPORT_DIR = resolve(
  process.env.DIRECTOR_EXPORT_DIR ?? join(process.cwd(), '..', 'agent', 'exports')
);

export async function GET(_request: Request, context: { params: Promise<{ filename: string }> }) {
  const { filename } = await context.params;

  if (basename(filename) !== filename || !/^export-[a-z0-9x-]+\.mp4$/i.test(filename)) {
    return NextResponse.json({ error: 'Invalid export filename' }, { status: 400 });
  }

  const filePath = join(EXPORT_DIR, filename);

  try {
    const file = await stat(filePath);
    if (!file.isFile()) {
      return NextResponse.json({ error: 'Export not found' }, { status: 404 });
    }

    return new Response(Readable.toWeb(createReadStream(filePath)) as ReadableStream, {
      headers: {
        'Content-Type': 'video/mp4',
        'Content-Length': String(file.size),
        'Content-Disposition': `attachment; filename="${filename}"`,
        'Cache-Control': 'private, no-store',
      },
    });
  } catch {
    return NextResponse.json({ error: 'Export not found' }, { status: 404 });
  }
}
