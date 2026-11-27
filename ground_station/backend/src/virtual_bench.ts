import fs from 'node:fs';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';

type Event = {
  kind?: string;
  capture_id?: number;
  snapshot_id?: string;
  images?: Record<string, string>;
};

export function virtualBench(rootPath: string) {
  const root = fs.realpathSync(rootPath);
  const eventFile = path.join(root, 'module-events.jsonl');

  function recentEvents(): Event[] {
    const fd = fs.openSync(eventFile, 'r');
    try {
      const size = fs.fstatSync(fd).size;
      const offset = Math.max(0, size - 1024 * 1024);
      const buffer = Buffer.alloc(size - offset);
      const count = fs.readSync(fd, buffer, 0, buffer.length, offset);
      const lines = buffer.subarray(0, count).toString('utf8').split('\n');
      if (offset) lines.shift();
      if (lines.at(-1) === '') lines.pop();
      const events: Event[] = [];
      for (const line of lines) {
        try {
          const event: unknown = JSON.parse(line);
          if (event && typeof event === 'object' && !Array.isArray(event)) events.push(event);
        } catch {
          // The simulator may still be writing the last line.
        }
      }
      return events;
    } finally {
      fs.closeSync(fd);
    }
  }

  return (request: IncomingMessage, response: ServerResponse, url: URL): boolean => {
    if (!url.pathname.startsWith('/api/virtual/')) return false;
    if (request.method !== 'GET' || !/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(request.headers.host ?? '')) {
      response.writeHead(403).end();
      return true;
    }
    try {
      const events = recentEvents();
      if (url.pathname === '/api/virtual/events') {
        response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        response.end(JSON.stringify(events.map(event => {
          if (!event.images) return event;
          const { images, ...metadata } = event;
          const capture = event.capture_id;
          return { ...metadata, images: Number.isSafeInteger(capture) ? {
            left: '/api/virtual/image?id=' + capture + '&side=left',
            right: '/api/virtual/image?id=' + capture + '&side=right',
          } : {} };
        })));
        return true;
      }
      if (url.pathname === '/api/virtual/image') {
        const capture = Number(url.searchParams.get('id'));
        const side = url.searchParams.get('side');
        if ((side === 'left' || side === 'right') && Number.isSafeInteger(capture) && capture > 0) {
          const event = [...events].reverse().find(event => event.kind === 'image_transfer' && event.capture_id === capture);
          const source = event?.images?.[side];
          if (typeof source === 'string') {
            const file = fs.realpathSync(source);
            const relative = path.relative(root, file);
            if (!relative.startsWith('..') && !path.isAbsolute(relative) &&
                path.basename(file) === side + '.png' && fs.statSync(file).isFile()) {
              response.writeHead(200, { 'Content-Type': 'image/png', 'Cache-Control': 'no-store' });
              fs.createReadStream(file).on('error', error => response.destroy(error)).pipe(response);
              return true;
            }
          }
        }
      }
    } catch {
      response.writeHead(404).end();
      return true;
    }
    response.writeHead(404).end();
    return true;
  };
}
