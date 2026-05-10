// Chapter marker patterns: 第X章, Chapter X, —X—, or numbered sections
const CHAPTER_PATTERNS = [
  /第[一二三四五六七八九十百千万\d]+章\s*(.*)/,
  /Chapter\s+(\d+)\s*[—–-]?\s*(.*)/i,
  /^\s*[-—]\s*(\d+)\s*[-—]\s*$/m,
  /^(\d+)\.\s+(.+)/m,
];

export interface DetectedChapter {
  index: number;
  title: string;
  text: string;
}

export function detectChapters(content: string): DetectedChapter[] {
  const lines = content.split('\n');
  const chapters: DetectedChapter[] = [];
  let currentChunk: string[] = [];
  let chapterIndex = 0;

  for (const line of lines) {
    let matched = false;
    for (const pattern of CHAPTER_PATTERNS) {
      const m = line.match(pattern);
      if (m) {
        if (currentChunk.length > 0 || chapters.length > 0) {
          const title = m[2]?.trim() || m[1]?.trim() || `Chapter ${chapterIndex + 1}`;
          chapters.push({
            index: chapterIndex,
            title: chapters.length === 0 ? title || `Chapter 1` : title || `Chapter ${chapters.length + 1}`,
            text: currentChunk.join('\n'),
          });
          chapterIndex++;
        } else {
          // First chapter — title is the matched line text, no content yet
          chapters.push({
            index: chapterIndex,
            title: m[2]?.trim() || m[1]?.trim() || 'Chapter 1',
            text: '',
          });
          chapterIndex++;
        }
        currentChunk = [];
        matched = true;
        break;
      }
    }
    if (!matched) {
      currentChunk.push(line);
    }
  }

  // Append remaining content to last chapter
  if (currentChunk.length > 0) {
    if (chapters.length > 0) {
      chapters[chapters.length - 1].text += '\n' + currentChunk.join('\n');
    } else {
      chapters.push({ index: 0, title: 'Chapter 1', text: currentChunk.join('\n') });
    }
  }

  return chapters;
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

export function createBookFromSource(
  title: string,
  sourcePath: string,
  sourceType: 'file' | 'web',
  content: string,
): import('../types').Book {
  const chapters = detectChapters(content);
  return {
    id: generateId(),
    title,
    sourcePath,
    sourceType,
    chapters: chapters.map(ch => ({
      index: ch.index,
      title: ch.title,
      status: 'ready' as const,
      content: ch.text || null,
    })),
    createdAt: Date.now(),
    currentChapter: 0,
    status: 'imported',
  };
}
