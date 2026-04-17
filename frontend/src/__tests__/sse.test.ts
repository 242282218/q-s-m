import { describe, expect, it, vi } from 'vitest';

import { consumeSse } from '@/lib/sse';

function buildResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    })
  );
}

describe('consumeSse', () => {
  it('throws when the browser response body is missing', async () => {
    await expect(
      consumeSse({ body: null } as Response, () => {
        throw new Error('should not emit');
      })
    ).rejects.toThrow('浏览器不支持流式响应');
  });

  it('parses chunked events and flushes the trailing buffered event', async () => {
    const events = [
      {
        type: 'log',
        data: { step: 1 },
        timestamp: '2026-04-17T00:00:00Z',
        request_id: null,
        message: 'first',
        level: 'info',
      },
      {
        type: 'complete',
        data: { step: 2 },
        timestamp: '2026-04-17T00:00:01Z',
        request_id: null,
        message: 'second',
        level: 'info',
      },
    ];

    const response = buildResponse([
      `data: ${JSON.stringify(events[0])}\n\n`,
      `data: ${JSON.stringify(events[1])}`.slice(0, 35),
      `data: ${JSON.stringify(events[1])}`.slice(35),
    ]);
    const received: unknown[] = [];

    await consumeSse(response, (envelope) => {
      received.push(envelope);
    });

    expect(received).toEqual(events);
  });

  it('skips malformed chunks and keeps later events alive', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const validEvent = {
      type: 'progress',
      data: { current: 1, total: 2 },
      timestamp: '2026-04-17T00:00:02Z',
      request_id: null,
      message: 'ok',
      level: 'info',
    };
    const received: unknown[] = [];

    await consumeSse(
      buildResponse([`data: not-json\n\n`, `data: ${JSON.stringify(validEvent)}\n\n`]),
      (envelope) => {
        received.push(envelope);
      }
    );

    expect(received).toEqual([validEvent]);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    warnSpy.mockRestore();
  });
});
