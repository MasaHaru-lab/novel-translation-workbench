export type ViewState = 'library' | 'preview' | 'translating' | 'reader';
export type SourceType = 'file' | 'web';
export type ChapterStatus = 'ready' | 'translating' | 'done' | 'error';
export type ThemeMode = 'light' | 'dark';

export interface Chapter {
  index: number;
  title: string;
  status: ChapterStatus;
  content: string | null;
}

export interface Book {
  id: string;
  title: string;
  sourcePath: string;
  sourceType: SourceType;
  chapters: Chapter[];
  createdAt: number;
  currentChapter: number;
  status: 'imported' | 'translating' | 'translated' | 'error';
}

export interface Highlight {
  id: string;
  chapterIndex: number;
  text: string;
  note: string;
  createdAt: number;
}

export interface ReaderSettings {
  fontSize: number;
  theme: ThemeMode;
}

export interface ImportSource {
  type: SourceType;
  path: string;
  content: string;
  title: string;
}
