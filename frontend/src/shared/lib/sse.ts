import type { SseEnvelope } from '@/types/api';

export async function consumeSse(
  response: Response,
  onEnvelope: (envelope: SseEnvelope) => void
): Promise<void> {
  if (!response.body) {
    throw new Error('浏览器不支持流式响应');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const emitChunk = (chunk: string) => {
    const lines = chunk.split(/\r?\n/);
    let raw = '';
    for (const line of lines) {
      if (line.startsWith('data:')) {
        raw += line.slice(5).trim();
      }
    }
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as SseEnvelope;
      onEnvelope(parsed);
    } catch (error) {
      // Keep stream alive even if one malformed chunk appears.
      console.warn('Skip invalid SSE payload chunk', error);
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() || '';
    chunks.forEach(emitChunk);
  }

  const rest = buffer.trim();
  if (rest) {
    emitChunk(rest);
  }
}
