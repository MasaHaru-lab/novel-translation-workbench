import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TranslationClient } from '../src/api/client';

describe('TranslationClient', () => {
  let client: TranslationClient;

  beforeEach(() => {
    client = new TranslationClient('http://test:9999');
    vi.restoreAllMocks();
  });

  it('translateChapter returns text on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ translated_text: 'Hello world' }), { status: 200 })
    );
    const result = await client.translateChapter('你好世界');
    expect(result).toBe('Hello world');
  });

  it('translateChapter throws on server error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Server Error', { status: 500 })
    );
    await expect(client.translateChapter('test')).rejects.toThrow(/Translation failed/);
  });

  it('health returns true when server responds', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('OK', { status: 200 }));
    expect(await client.health()).toBe(true);
  });

  it('health returns false on network error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'));
    expect(await client.health()).toBe(false);
  });
});
