const DEFAULT_BASE_URL = 'http://localhost:8000';

export class TranslationClient {
  private baseUrl: string;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  async translateChapter(source: string): Promise<string> {
    const res = await fetch(`${this.baseUrl}/translate/chapter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_text: source }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Translation failed: ${res.status} ${text}`);
    }
    const data = await res.json();
    return data.translated_text ?? data.translation ?? '';
  }

  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/health`, { method: 'GET' });
      return res.ok;
    } catch {
      return false;
    }
  }
}

export const translationApi = new TranslationClient();
