// __tests__/contentParser.test.ts
import { describe, it, expect } from 'vitest';
import { detectChapters, createBookFromSource } from '../src/utils/contentParser';

describe('detectChapters', () => {
  it('detects 第X章 pattern', () => {
    const input = '第1章 山村\nText here.\n第2章 城里\nMore text.';
    const result = detectChapters(input);
    expect(result).toHaveLength(2);
    expect(result[0].title).toBe('山村');
    expect(result[1].title).toBe('城里');
  });

  it('detects Chapter X pattern', () => {
    const input = 'Chapter 1 — The Start\nContent.\nChapter 2 — The End\nMore.';
    const result = detectChapters(input);
    expect(result).toHaveLength(2);
    expect(result[0].title).toBe('The Start');
  });

  it('treats whole file as one chapter when no markers found', () => {
    const input = 'Just some text.\nNo chapter markers here.';
    const result = detectChapters(input);
    expect(result).toHaveLength(1);
    expect(result[0].title).toBe('Chapter 1');
  });

  it('creates book with correct chapter count', () => {
    const book = createBookFromSource('Test Book', '/path.txt', 'file', '前言\n第1章 A\nx\n第2章 B\ny');
    expect(book.title).toBe('Test Book');
    expect(book.chapters).toHaveLength(2);
    expect(book.status).toBe('imported');
    expect(book.chapters[0].status).toBe('ready');
    expect(book.chapters[0].content).toBe('前言');
  });
});
