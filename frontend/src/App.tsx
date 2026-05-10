import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Upload,
  FileText,
  Layers,
  Zap,
  ArrowRight,
  Play,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  Type,
  Minus,
  Plus,
  Languages,
  ArrowLeft,
  Settings2,
  BrainCircuit,
  Info,
  ChevronRight,
  Download,
  Maximize2,
  Book,
  ShieldCheck,
  Search,
  Volume2,
  Sparkles,
  Coffee,
  XCircle,
  X,
  Loader2,
  RefreshCw
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

// --- Types ---

type AppView = 'library' | 'reader' | 'quick-translate' | 'profile';
type Language = 'en' | 'cn';

interface AudioSettings {
  clicksEnabled: boolean;
  pageTurnEnabled: boolean;
  selectedSound: number;
}

interface Finding {
  id: string;
  type: 'issue' | 'rule';
  title: string;
  description: string;
  icon: any;
  color: 'amber' | 'lavender';
}

interface StreamChapter {
  index: number;
  title: string;
  sourceText: string;
  translatedText?: string;
  status: 'pending' | 'translating' | 'complete' | 'error';
  error?: string;
}

interface Book {
  id: string;
  title: string;
  chapters: StreamChapter[];
  createdAt: number;
  totalChapters: number;
  completedChapters: number;
  isStreaming: boolean;
}

interface UploadedFile {
  name: string;
  size: string;
  content: string;
  file: File;
}

interface ReaderConfig {
  fontSize: number;
  lineSpacing: 'relaxed' | 'tight';
  isBilingual: boolean;
}

type ReaderBlock = {
  id: string;
  type: 'heading' | 'paragraph';
  text: string;
  level?: number;
  sourceIndex?: number;
};

const API_BASE_URL = ((import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

interface BookDetailResponse {
  book: {
    book_id: string;
    title: string;
    source_filename: string;
    detected_chapter_count: number;
    created_at: string;
  };
  job: {
    status: string;
    detected_chapter_count: number;
    completed_chapter_indexes: number[];
    failed_chapter_indexes: number[];
    error_message?: string | null;
  };
  chapters: Array<{
    index: number;
    heading: string;
  }>;
}

interface ChapterContentResponse {
  book_id: string;
  index: number;
  heading: string;
  source_text: string;
  translation?: {
    text: string;
    output_filename: string;
  } | null;
}

interface TranslateNextResponse {
  book_id: string;
  ran_index: number | null;
  success: boolean;
  chapter_status?: string | null;
  error_message?: string | null;
  book: BookDetailResponse;
}

const UI_STRINGS = {
  en: {
    quickTranslate: 'Quick Translate',
    library: 'Library',
    profile: 'Producer Profile',
    newBook: '+ New',
    uploadTitle: 'Upload New Book',
    bookTitle: 'Book Title',
    bookTitlePlaceholder: 'Enter book title...',
    author: 'Author',
    authorPlaceholder: 'Optional author name...',
    dropFile: 'Drop .txt or .md file here',
    uploading: 'Uploading...',
    startTranslation: 'Start Translation',
    cancel: 'Cancel',
    backToLibrary: 'Back to Library',
    chapter: 'Chapter',
    of: 'of',
    translated: 'translated',
    pending: 'Pending',
    translating: 'Translating...',
    translationFailed: 'Translation failed',
    sourceOnly: 'Source text (translation pending)',
    sourcePreview: 'Source Preview',
    transPipeline: 'Translation Pipeline',
    statusPill: 'Local Prototype',
    waiting: 'just a sec, ready soon...',
    abandon: 'Abandon Session',
    abandonConfirm: 'Abandon this session and start a new upload?',
    homeConfirm: 'Return to library? Reading progress is saved.',
    readerInspector: 'Review & Memory',
    download: 'Download Chapter',
    fullscreen: 'Toggle Fullscreen',
    bilingual: 'Bilingual',
    monolingual: 'Monolingual',
    progress: 'Progress',
    prev: 'Prev',
    next: 'Next',
    page: 'Page',
    audio: 'Audio Settings',
    uiLang: 'Interface Language',
    clicks: 'Key Clicks',
    pageTurn: 'Page Turn',
    soundProfile: 'Sound Profile',
    emptyLibrary: 'No books yet. Click "+ New" to upload and translate.',
    volumes: 'VOLUMES',
    openBook: 'Open Book',
    removeBook: 'Remove',
    retry: 'Retry',
  },
  cn: {
    quickTranslate: '现译现看',
    library: '书架',
    profile: '制作者个人主页',
    newBook: '+ 新建',
    uploadTitle: '上传新书',
    bookTitle: '书名',
    bookTitlePlaceholder: '输入书名...',
    author: '作者',
    authorPlaceholder: '可选作者名...',
    dropFile: '拖放 .txt 或 .md 文件到此处',
    uploading: '上传中...',
    startTranslation: '开始翻译',
    cancel: '取消',
    backToLibrary: '返回书架',
    chapter: '章',
    of: '/',
    translated: '已翻译',
    pending: '等待中',
    translating: '翻译中...',
    translationFailed: '翻译失败',
    sourceOnly: '原文（翻译等待中）',
    sourcePreview: '原文预览',
    transPipeline: '翻译流水线',
    statusPill: '本地原型',
    waiting: '稍等片刻，美好即将呈现。。。',
    abandon: '清空会话',
    abandonConfirm: '放弃当前会话并重新上传？',
    homeConfirm: '返回书架？当前进度将保留。',
    readerInspector: '审阅与记忆',
    download: '下载章节',
    fullscreen: '全屏切换',
    bilingual: '双语对照',
    monolingual: '单语模式',
    progress: '阅读进度',
    prev: '上一页',
    next: '下一页',
    page: '页码',
    audio: '声音设置',
    uiLang: '界面语言',
    clicks: '按键音开关',
    pageTurn: '翻书声音开关',
    soundProfile: '声音选项',
    emptyLibrary: '书架还是空的。点击"+ 新建"上传和翻译。',
    volumes: '本',
    openBook: '打开',
    removeBook: '删除',
    retry: '重试',
  }
};

// --- Mock Data ---

const findings: Finding[] = [
  { id: '1', type: 'issue', title: 'Context Conflict', description: 'The term "Gong" refers to a title here, not the surname used in Ch 12.', icon: AlertCircle, color: 'amber' },
  { id: '2', type: 'rule', title: 'Style Guide Match', description: 'Internal monologue normalized to italic font-serif.', icon: CheckCircle2, color: 'lavender' },
  { id: '3', type: 'issue', title: 'Archetype Sync', description: 'Dialogue register for character "Wei" updated to formal-archaic.', icon: Zap, color: 'amber' },
];

const stages = [
  { id: '1', label: 'Semantic Extraction', status: 'completed' },
  { id: '2', label: 'Lexicon Alignment', status: 'completed' },
  { id: '3', label: 'Drafting (Atlas-13B)', status: 'processing' },
  { id: '4', label: 'Cultural Sensitivity Check', status: 'waiting' },
];

// --- Helpers ---

let bookIdCounter = Date.now();
function generateBookId(): string {
  return `book-${bookIdCounter++}`;
}

const parseReaderBlocks = (text: string): ReaderBlock[] => {
  const blocks: ReaderBlock[] = [];
  const paragraphLines: string[] = [];
  let sourceIndex = 0;

  const flushParagraph = () => {
    const text = paragraphLines.join('\n').trim();
    if (!text) return;
    blocks.push({ id: `p-${blocks.length}`, type: 'paragraph', text, sourceIndex });
    sourceIndex += 1;
    paragraphLines.length = 0;
  };

  text.split(/\r?\n/).forEach((line) => {
    const heading = /^(#{1,6})\s+(.+)$/.exec(line.trim());
    if (heading) {
      flushParagraph();
      blocks.push({ id: `h-${blocks.length}`, type: 'heading', level: heading[1].length, text: heading[2].trim() });
      return;
    }
    if (!line.trim()) { flushParagraph(); return; }
    paragraphLines.push(line);
  });

  flushParagraph();
  return blocks;
};

const paragraphsToReaderBlocks = (paragraphs: string[]): ReaderBlock[] =>
  paragraphs.map((text, index) => ({ id: `p-${index}`, type: 'paragraph', text, sourceIndex: index }));

const readApiError = async (response: Response): Promise<string> => {
  const body = await response.json().catch(() => null);
  return body?.detail || `Request failed with ${response.status}`;
};

const mapBookDetail = (detail: BookDetailResponse, previous?: Book): Book => {
  const previousByIndex = new Map(previous?.chapters.map(ch => [ch.index, ch]) || []);
  const completed = new Set(detail.job.completed_chapter_indexes);
  const failed = new Set(detail.job.failed_chapter_indexes);

  const chapters = detail.chapters.map((entry) => {
    const existing = previousByIndex.get(entry.index);
    const status: StreamChapter['status'] = completed.has(entry.index)
      ? 'complete'
      : failed.has(entry.index)
        ? 'error'
        : existing?.status === 'translating'
          ? 'translating'
          : 'pending';
    return {
      index: entry.index,
      title: entry.heading || `Chapter ${entry.index}`,
      sourceText: existing?.sourceText || '',
      translatedText: existing?.translatedText,
      status,
      error: failed.has(entry.index) ? detail.job.error_message || existing?.error : existing?.error,
    };
  });

  return {
    id: detail.book.book_id,
    title: detail.book.title || detail.book.source_filename,
    chapters,
    createdAt: Date.parse(detail.book.created_at) || previous?.createdAt || Date.now(),
    totalChapters: chapters.length || detail.job.detected_chapter_count || detail.book.detected_chapter_count,
    completedChapters: detail.job.completed_chapter_indexes.length,
    isStreaming: detail.job.status === 'running' || detail.job.status === 'partial',
  };
};

const applyChapterContent = (book: Book, chapter: ChapterContentResponse): Book => ({
  ...book,
  chapters: book.chapters.map(ch => ch.index === chapter.index ? {
    ...ch,
    title: chapter.heading || ch.title,
    sourceText: chapter.source_text,
    translatedText: chapter.translation?.text || ch.translatedText,
    status: chapter.translation ? 'complete' : ch.status,
  } : ch),
});

// --- Sub-components ---

const Panel = ({ title, children, icon: Icon, headerAction }: { title: string; children: React.ReactNode; icon: any, headerAction?: React.ReactNode }) => (
  <div className="flex-1 flex flex-col bg-white dark:bg-dark-surface border border-card-border rounded-[32px] shadow-sm overflow-hidden min-w-0">
    <div className="p-6 border-b border-card-border flex items-center justify-between bg-stone-50/50 dark:bg-stone-900/10">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-white dark:bg-charcoal border border-card-border text-dusty-blue shadow-sm"><Icon size={16} /></div>
        <h3 className="text-xs font-bold uppercase tracking-widest text-warm-gray">{title}</h3>
      </div>
      {headerAction}
    </div>
    <div className="flex-1 p-8 overflow-y-auto custom-scrollbar">{children}</div>
  </div>
);

const ControlItem = ({ label, value, icon: Icon }: { label: string; value: string; icon?: any }) => (
  <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-stone-50 dark:bg-stone-900/50 border border-card-border/50">
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-stone-300 uppercase tracking-widest leading-none mb-1">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-bold text-charcoal dark:text-white">{value}</span>
        {Icon && <Icon size={12} className="text-dusty-blue" />}
      </div>
    </div>
  </div>
);

const TypingPlaceholder = ({ text }: { text: string }) => {
  const [visibleCount, setVisibleCount] = useState(0);
  const words = text.split(' ');
  useEffect(() => {
    const interval = setInterval(() => setVisibleCount(prev => (prev + 1) % (words.length + 5)), 200);
    return () => clearInterval(interval);
  }, [words.length]);
  return (
    <div className="flex flex-wrap gap-2 opacity-20">
      {words.map((word, i) => (
        <span key={i} className={`transition-opacity duration-300 ${i < visibleCount ? 'opacity-100' : 'opacity-0'}`}>{word}</span>
      ))}
    </div>
  );
};

const FrostedMist = () => (
  <div className="relative w-full h-8 flex items-center justify-center overflow-hidden">
    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-dusty-blue/10 to-transparent animate-[mist-rise_3s_infinite]" />
    <div className="flex gap-2">
      {[1, 2, 3].map(i => (
        <motion.div key={i} animate={{ scale: [1, 1.3, 1], opacity: [0.3, 0.7, 0.3] }}
          transition={{ repeat: Infinity, duration: 2, delay: i * 0.4 }}
          className="w-1.5 h-1.5 rounded-full bg-dusty-blue" />
      ))}
    </div>
  </div>
);

const StatusPill = ({ children }: { children: React.ReactNode }) => (
  <div className="px-3 py-1 rounded-full bg-dusty-blue/10 border border-dusty-blue/20 flex items-center gap-2">
    <div className="w-1.5 h-1.5 rounded-full bg-dusty-blue animate-pulse" />
    <span className="text-[10px] font-bold uppercase tracking-widest text-dusty-blue">{children}</span>
  </div>
);

const MistOverlay = ({ stages }: { stages: any[] }) => (
  <div className="h-full flex flex-col items-center justify-center p-8 space-y-8">
    <div className="relative">
      <div className="absolute inset-0 bg-dusty-blue/20 blur-3xl rounded-full scale-150 animate-pulse" />
      <FrostedMist />
    </div>
    <div className="w-full max-w-xs space-y-4">
      {stages.map((s, i) => (
        <div key={i} className="flex items-center justify-between">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${s.status === 'processing' ? 'text-charcoal dark:text-white' : 'text-warm-gray'}`}>{s.label}</span>
          {s.status === 'completed' ? <CheckCircle2 size={12} className="text-sage" /> :
            s.status === 'processing' ? <div className="w-2 h-2 rounded-full bg-dusty-blue animate-ping" /> :
              <div className="w-2 h-2 rounded-full bg-stone-200" />}
        </div>
      ))}
    </div>
  </div>
);

// --- Upload Modal ---

const UploadModal = ({ lang, onUpload, onCancel, playActionSound }: {
  lang: Language;
  onUpload: (title: string, author: string, file: UploadedFile) => void;
  onCancel: () => void;
  playActionSound: (t: 'click') => void;
}) => {
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const t = UI_STRINGS[lang];

  const handleFile = (f: File) => {
    setError(null);
    const ext = f.name.split('.').pop()?.toLowerCase();
    if (ext !== 'txt' && ext !== 'md') {
      setError("Unsupported format. Please use .txt or .md.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      if (!title) setTitle(f.name.replace(/\.[^/.]+$/, ""));
      setFile({ name: f.name, size: `${(f.size / 1024).toFixed(1)} KB`, content, file: f });
    };
    reader.readAsText(f);
  };

  const handleUpload = () => {
    playActionSound('click');
    if (!file) { setError("Please select a file."); return; }
    onUpload(title || file.name.replace(/\.[^/.]+$/, ""), author, file);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/20 backdrop-blur-sm p-4"
      onClick={(e: React.MouseEvent<HTMLDivElement>) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="bg-white dark:bg-dark-surface border border-card-border rounded-[32px] shadow-2xl w-full max-w-lg overflow-hidden"
      >
        <div className="p-6 border-b border-card-border flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-widest text-charcoal dark:text-white">{t.uploadTitle}</h3>
          <button onClick={onCancel} className="p-2 rounded-xl hover:bg-stone-100 dark:hover:bg-stone-800 text-warm-gray">
            <X size={16} />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[9px] font-bold uppercase tracking-widest text-warm-gray">{t.bookTitle}</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t.bookTitlePlaceholder}
                className="w-full px-4 py-2.5 rounded-xl bg-stone-50 dark:bg-stone-900 border border-card-border text-sm text-charcoal dark:text-white placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-dusty-blue/30"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[9px] font-bold uppercase tracking-widest text-warm-gray">{t.author}</label>
              <input
                type="text"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder={t.authorPlaceholder}
                className="w-full px-4 py-2.5 rounded-xl bg-stone-50 dark:bg-stone-900 border border-card-border text-sm text-charcoal dark:text-white placeholder:text-stone-300 focus:outline-none focus:ring-2 focus:ring-dusty-blue/30"
              />
            </div>
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setIsDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
            onClick={() => fileInputRef.current?.click()}
            className={`relative border-2 border-dashed rounded-2xl py-8 flex flex-col items-center justify-center cursor-pointer transition-all ${
              isDragOver ? 'border-dusty-blue bg-dusty-blue/5' : 'border-card-border hover:border-dusty-blue/50'
            }`}
          >
            <input ref={fileInputRef} type="file" className="hidden" accept=".txt,.md" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
            {file ? (
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-sage/10 text-sage"><FileText size={20} /></div>
                <div className="text-left">
                  <p className="text-sm font-bold text-charcoal dark:text-white">{file.name}</p>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-warm-gray">{file.size}</p>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 text-warm-gray">
                <Upload size={24} className="text-stone-300" />
                <p className="text-sm font-medium">{t.dropFile}</p>
              </div>
            )}
          </div>

          {error && <p className="text-rose-500 text-xs font-medium">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button onClick={onCancel} className="flex-1 py-3 rounded-xl border border-card-border text-[10px] font-bold uppercase tracking-widest text-warm-gray hover:bg-stone-50 dark:hover:bg-stone-800 transition-all">
              {t.cancel}
            </button>
            <button
              onClick={handleUpload}
              disabled={!file}
              className={`flex-1 py-3 rounded-xl text-[10px] font-bold uppercase tracking-widest transition-all flex items-center justify-center gap-2 ${
                file ? 'bg-charcoal text-white shadow-lg hover:bg-dusty-blue' : 'bg-stone-100 text-stone-300 cursor-not-allowed'
              }`}
            >
              <Play size={12} fill="currentColor" /> {t.startTranslation}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

// --- Book Reader ---

const BookReaderView = ({ book, lang, readerConfig, setReaderConfig, showInspector, setShowInspector, audioSettings, playActionSound, onBack, onLoadChapter, isFullscreen }: {
  book: Book;
  lang: Language;
  readerConfig: ReaderConfig;
  setReaderConfig: (c: ReaderConfig) => void;
  showInspector: boolean;
  setShowInspector: (v: boolean) => void;
  audioSettings: AudioSettings;
  playActionSound: (type: 'click' | 'page') => void;
  onBack: () => void;
  onLoadChapter: (index: number) => void;
  isFullscreen: boolean;
}) => {
  const [currentChapterIdx, setCurrentChapterIdx] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageDirection, setPageDirection] = useState(1);
  const contentRef = useRef<HTMLDivElement>(null);
  const [showControls, setShowControls] = useState(true);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleReaderMouseMove = useCallback(() => {
    if (!isFullscreen) return;
    setShowControls(true);
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    hideTimerRef.current = setTimeout(() => setShowControls(false), 2500);
  }, [isFullscreen]);

  useEffect(() => {
    if (!isFullscreen) setShowControls(true);
  }, [isFullscreen]);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, []);

  const t = UI_STRINGS[lang];
  const blocksPerPage = isFullscreen ? 40 : 20;

  const currentChapter = book.chapters[currentChapterIdx];
  const isTranslated = currentChapter?.status === 'complete';
  const isError = currentChapter?.status === 'error';
  const isPending = currentChapter?.status === 'pending';
  const isTranslating = currentChapter?.status === 'translating';

  const displayText = isTranslated && currentChapter.translatedText
    ? currentChapter.translatedText
    : currentChapter?.sourceText || '';

  const displayBlocks = displayText ? parseReaderBlocks(displayText) : [];

  const pageCount = Math.max(1, Math.ceil(displayBlocks.length / blocksPerPage));
  const startIndex = (currentPage - 1) * blocksPerPage;
  const pageBlocks = displayBlocks.slice(startIndex, startIndex + blocksPerPage);
  const leftBlocks = pageBlocks.slice(0, Math.ceil(pageBlocks.length / 2));
  const rightBlocks = pageBlocks.slice(Math.ceil(pageBlocks.length / 2));

  useEffect(() => {
    setCurrentPage(1);
  }, [currentChapterIdx]);

  useEffect(() => {
    if (currentChapter) onLoadChapter(currentChapter.index);
  }, [currentChapter?.index, onLoadChapter]);

  useEffect(() => {
    if (currentPage > pageCount) setCurrentPage(pageCount);
  }, [currentPage, pageCount]);

  const toggleFullscreen = () => {
    playActionSound('click');
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  };

  const completedCount = book.chapters.filter(c => c.status === 'complete').length;
  const progressPct = book.totalChapters > 0 ? Math.round((completedCount / book.totalChapters) * 100) : 0;

  return (
    <div className={`flex flex-col ${isFullscreen ? 'gap-0 min-h-screen' : 'gap-2 min-h-[calc(100vh-120px)] lg:h-[calc(100vh-120px)]'} animate-in fade-in zoom-in-95 duration-700`} onMouseMove={handleReaderMouseMove}>
      {/* Top bar: back, title, chapter nav, controls */}
      <div className={`flex flex-wrap items-center justify-between px-3 lg:px-5 py-2 bg-white/40 backdrop-blur-md border border-card-border rounded-2xl shadow-sm gap-2 transition-all duration-300 ${isFullscreen && !showControls ? 'opacity-0 min-h-0 h-0 py-0 border-0 overflow-hidden pointer-events-none' : 'opacity-100'}`}>
        <div className="flex items-center gap-4">
          <button onClick={() => { playActionSound('click'); onBack(); }}
            className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-warm-gray hover:text-charcoal border-r border-card-border pr-6"
          >
            <ArrowLeft size={14} /> {t.backToLibrary}
          </button>
          <div className="flex flex-col">
            <h2 className="text-sm font-bold text-charcoal dark:text-white leading-tight">{book.title}</h2>
            <div className="flex items-center gap-3">
              <span className="text-[9px] font-bold text-warm-gray">{currentChapter?.title}</span>
              <span className="text-[9px] text-stone-300">•</span>
              <span className="text-[9px] font-bold text-sage">{completedCount}/{book.totalChapters} {t.translated}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Chapter selector */}
          <div className="flex items-center gap-1.5">
            {book.chapters.slice(0, Math.min(book.chapters.length, 20)).map((ch, idx) => (
              <button
                key={ch.index}
                onClick={() => { playActionSound('click'); setCurrentChapterIdx(idx); }}
                className={`w-7 h-7 rounded-lg text-[9px] font-bold transition-all flex items-center justify-center ${
                  idx === currentChapterIdx
                    ? 'bg-charcoal text-white dark:bg-white dark:text-charcoal'
                    : ch.status === 'complete'
                      ? 'bg-sage/10 text-sage border border-sage/20'
                      : ch.status === 'error'
                        ? 'bg-rose-50 text-rose-500 border border-rose-200'
                        : 'bg-stone-50 dark:bg-stone-900 text-stone-300 border border-card-border/50'
                }`}
                title={`${ch.title} - ${ch.status}`}
              >
                {ch.status === 'complete' ? '✓' : ch.status === 'error' ? '!' : idx + 1}
              </button>
            ))}
            {book.chapters.length > 20 && <span className="text-[9px] text-stone-300 ml-1">+{book.chapters.length - 20}</span>}
          </div>

          {book.isStreaming && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dusty-blue/5 border border-dusty-blue/15">
              <Loader2 size={12} className="text-dusty-blue animate-spin" />
              <span className="text-[9px] font-bold text-dusty-blue">{progressPct}%</span>
            </div>
          )}

          <div className="h-6 w-px bg-card-border" />

          <button onClick={() => { playActionSound('click'); setReaderConfig({ ...readerConfig, fontSize: Math.max(14, readerConfig.fontSize - 2) }); }}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800"><Minus size={14} /></button>
          <span className="text-xs font-bold w-6 text-center text-charcoal dark:text-white">{readerConfig.fontSize}</span>
          <button onClick={() => { playActionSound('click'); setReaderConfig({ ...readerConfig, fontSize: Math.min(32, readerConfig.fontSize + 2) }); }}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800"><Plus size={14} /></button>

          <button onClick={() => { playActionSound('click'); setReaderConfig({ ...readerConfig, isBilingual: !readerConfig.isBilingual }); }}
            className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-lg border transition-all ${
              readerConfig.isBilingual ? 'bg-dusty-blue text-white border-dusty-blue' : 'bg-white dark:bg-dark-surface text-warm-gray border-card-border'
            }`}>
            {readerConfig.isBilingual ? t.bilingual : t.monolingual}
          </button>


          <button onClick={() => { playActionSound('click'); setShowInspector(!showInspector); }}
            className={`flex items-center gap-2 text-[10px] font-black uppercase tracking-widest transition-colors ${showInspector ? 'text-lavender' : 'text-warm-gray hover:text-charcoal'}`}>
            <BrainCircuit size={14} /> <span className="hidden sm:inline">{t.readerInspector}</span>
          </button>
          <button onClick={toggleFullscreen} title={t.fullscreen} className="p-2 rounded-lg text-warm-gray hover:text-charcoal"><Maximize2 size={16} /></button>
        </div>
      </div>

      {/* Progress bar */}
      <div className={`px-4 lg:px-8 transition-all duration-300 ${isFullscreen && !showControls ? 'opacity-0 min-h-0 h-0 overflow-hidden' : 'opacity-100'}`}>
        <div className="w-full h-1 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
          <div className="h-full bg-sage transition-all duration-500" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      {/* Main reading area */}
      <div className="flex flex-row gap-3 flex-1 min-h-0">
        <div className="flex-1 bg-white dark:bg-dark-surface border border-card-border rounded-[32px] shadow-sm relative flex flex-col overflow-y-auto">
          {currentChapter ? (
            <>
              <div ref={contentRef} className={`flex-1 flex flex-col mx-auto w-full relative ${isFullscreen ? 'max-w-none' : 'max-w-6xl'} ${isFullscreen ? 'px-4 py-2 lg:px-8 lg:py-4' : 'px-8 pt-8 pb-12 lg:px-20 lg:pt-10 lg:pb-10'}`}>
                {/* Chapter status badge */}
                {!isFullscreen && isPending && (
                  <div className="mb-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-stone-50 dark:bg-stone-900 border border-card-border">
                    <Loader2 size={12} className="text-dusty-blue animate-spin" />
                    <span className="text-[9px] font-bold uppercase tracking-widest text-warm-gray">{t.translating}</span>
                  </div>
                )}
                {!isFullscreen && isError && (
                  <div className="mb-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 dark:bg-rose-900/20 border border-rose-200">
                    <AlertCircle size={12} className="text-rose-500" />
                    <span className="text-[9px] font-bold uppercase tracking-widest text-rose-500">{t.translationFailed}</span>
                    {currentChapter.error && <span className="text-[9px] text-rose-400 ml-2">({currentChapter.error})</span>}
                  </div>
                )}
                {!isFullscreen && isTranslated && (
                  <div className="mb-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-sage/5 border border-sage/10">
                    <CheckCircle2 size={12} className="text-sage" />
                    <span className="text-[9px] font-bold uppercase tracking-widest text-sage">{t.translated}</span>
                  </div>
                )}

                {!isFullscreen && !isTranslated && !isError && (
                  <div className="mb-3 flex items-center gap-2 px-3 py-1 rounded-lg bg-amber/10 border border-amber/20">
                    <BookOpen size={12} className="text-amber" />
                    <span className="text-[9px] font-bold uppercase tracking-widest text-amber">{t.sourceOnly}</span>
                  </div>
                )}

                <AnimatePresence mode="wait">
                  <motion.div
                    key={`page-${currentChapterIdx}-${currentPage}`}
                    initial={{ opacity: 0, x: pageDirection * 28, filter: 'blur(2px)' }}
                    animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
                    exit={{ opacity: 0, x: pageDirection * -22, filter: 'blur(2px)' }}
                    transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                    className={`flex-1 flex flex-col ${isFullscreen ? 'space-y-1' : 'space-y-2'}`}
                  >
                    {!isFullscreen && (
                    <header className="text-center mb-2">
                      <p className="text-[9px] font-bold uppercase tracking-[0.3em] text-warm-gray">{currentChapter.title}</p>
                    </header>
                    )}
                    <div className={`font-serif text-charcoal dark:text-[#cbd5e1] leading-relaxed ${isFullscreen ? 'space-y-1' : 'space-y-2'}`} style={{ fontSize: `${readerConfig.fontSize}px` }}>
                      {pageBlocks.length > 0 ? (
                        <div className="grid grid-cols-2 gap-6">
                          <div className="space-y-4">
                            {leftBlocks.map((block) => {
                              if (block.type === 'heading') {
                                const headingClass = block.level === 1 ? 'text-3xl lg:text-4xl mt-2' : block.level === 2 ? 'text-2xl lg:text-3xl mt-4' : 'text-xl lg:text-2xl mt-2';
                                return <h3 key={block.id} className={`${headingClass} text-left font-serif text-charcoal dark:text-white leading-tight`}>{block.text}</h3>;
                              }
                              return (
                                <div key={block.id} className="space-y-4 group">
                                  <p className="text-left whitespace-pre-line">{block.text}</p>
                                  {readerConfig.isBilingual && isTranslated && currentChapter.sourceText && (
                                    <p className="text-sm font-sans text-warm-gray italic opacity-60 border-l-2 border-stone-100 dark:border-stone-800 pl-6 py-2 transition-all hover:opacity-100 whitespace-pre-line">
                                      {parseReaderBlocks(currentChapter.sourceText)[block.sourceIndex || 0]?.text || ''}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                          <div className="border-l border-card-border pl-6 space-y-4">
                            {rightBlocks.map((block) => {
                              if (block.type === 'heading') {
                                const headingClass = block.level === 1 ? 'text-3xl lg:text-4xl mt-2' : block.level === 2 ? 'text-2xl lg:text-3xl mt-4' : 'text-xl lg:text-2xl mt-2';
                                return <h3 key={block.id} className={`${headingClass} text-left font-serif text-charcoal dark:text-white leading-tight`}>{block.text}</h3>;
                              }
                              return (
                                <div key={block.id} className="space-y-4 group">
                                  <p className="text-left whitespace-pre-line">{block.text}</p>
                                  {readerConfig.isBilingual && isTranslated && currentChapter.sourceText && (
                                    <p className="text-sm font-sans text-warm-gray italic opacity-60 border-l-2 border-stone-100 dark:border-stone-800 pl-6 py-2 transition-all hover:opacity-100 whitespace-pre-line">
                                      {parseReaderBlocks(currentChapter.sourceText)[block.sourceIndex || 0]?.text || ''}
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <p className="text-center text-warm-gray italic py-20">(no content)</p>
                      )}
                    </div>
                  </motion.div>
                </AnimatePresence>
              </div>

              {/* Page navigation */}
              <div className={`border-t border-card-border flex items-center justify-between px-4 sm:px-6 lg:px-8 bg-stone-50/95 dark:bg-stone-900/95 z-10 transition-all duration-300 ${isFullscreen ? (showControls ? 'py-1.5' : 'min-h-0 h-0 py-0 border-0 overflow-hidden opacity-0') : 'py-2'}`}>
                <button disabled={currentPage === 1}
                  onClick={() => { playActionSound('page'); setPageDirection(-1); setCurrentPage(prev => prev - 1); }}
                  className={`text-[10px] font-black uppercase tracking-widest flex items-center gap-1.5 ${currentPage === 1 ? 'text-stone-200 dark:text-stone-700 cursor-not-allowed' : 'text-warm-gray hover:text-charcoal'}`}>
                  <ArrowLeft size={12} /> {t.prev}
                </button>
                <div className="text-[10px] font-black tracking-widest text-charcoal/40 dark:text-white/20 uppercase">
                  {t.page} <span className="text-charcoal dark:text-white">{currentPage}</span> / {pageCount}
                </div>
                <button disabled={currentPage === pageCount}
                  onClick={() => { playActionSound('page'); setPageDirection(1); setCurrentPage(prev => prev + 1); }}
                  className={`text-[10px] font-black uppercase tracking-widest flex items-center gap-1.5 ${currentPage === pageCount ? 'text-stone-200 dark:text-stone-700 cursor-not-allowed' : 'text-warm-gray hover:text-charcoal'}`}>
                  {currentPage === pageCount ? 'End' : t.next} <ArrowRight size={12} />
                </button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-warm-gray italic font-serif">
              No chapters available
            </div>
          )}
        </div>

        {/* Inspector sidebar */}
        <AnimatePresence>
          {showInspector && (
            <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 340, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
              className="border border-card-border rounded-[32px] card-blur shadow-sm overflow-hidden flex flex-col shrink-0">
              <div className="p-6 border-b border-card-border flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-widest text-warm-gray">{t.readerInspector}</h3>
                <button onClick={() => setShowInspector(false)} className="text-stone-300 hover:text-charcoal"><ChevronRight size={16} /></button>
              </div>
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {findings.map((f) => (
                  <div key={f.id} className={`p-4 rounded-2xl border border-card-border/50 text-left ${f.color === 'amber' ? 'bg-amber/5' : 'bg-lavender/5'}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`p-1.5 rounded-lg ${f.color === 'amber' ? 'bg-amber/20 text-amber' : 'bg-lavender/20 text-lavender'}`}><f.icon size={12} /></div>
                      <h4 className="text-[9px] font-bold uppercase tracking-widest text-warm-gray">{f.title}</h4>
                    </div>
                    <p className="text-xs font-medium text-charcoal dark:text-[#e2e8f0] leading-snug">{f.description}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

// --- Library View ---

const LibraryView = ({ books, onOpenBook, onRemoveBook, lang }: {
  books: Book[];
  onOpenBook: (id: string) => void;
  onRemoveBook: (id: string) => void;
  lang: Language;
}) => {
  const t = UI_STRINGS[lang];

  if (books.length === 0) {
    return (
      <div className="max-w-6xl mx-auto animate-in fade-in duration-700 pb-20">
        <header className="flex items-end justify-between border-b border-card-border pb-6 text-left">
          <div>
            <h2 className="text-3xl font-serif text-charcoal dark:text-white">{t.library}</h2>
            <p className="text-warm-gray text-xs mt-2 uppercase tracking-widest font-bold">{t.emptyLibrary}</p>
          </div>
        </header>
        <div className="mt-20 flex flex-col items-center justify-center text-center opacity-40">
          <Book size={64} className="text-stone-300 mb-6" />
          <p className="font-serif italic text-lg text-warm-gray">{t.emptyLibrary}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-10 animate-in fade-in duration-700 pb-20">
      <header className="flex items-end justify-between border-b border-card-border pb-6 text-left">
        <div>
          <h2 className="text-3xl font-serif text-charcoal dark:text-white">{t.library}</h2>
          <p className="text-warm-gray text-xs mt-2 uppercase tracking-widest font-bold">{t.volumes}</p>
        </div>
        <div className="px-5 py-2 bg-white dark:bg-dark-surface rounded-xl border border-card-border text-[10px] uppercase font-bold text-warm-gray">
          {books.length} {t.volumes}
        </div>
      </header>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {books.map((book) => {
          const completedCount = book.chapters.filter(c => c.status === 'complete').length;
          const progressPct = book.totalChapters > 0 ? Math.round((completedCount / book.totalChapters) * 100) : 0;
          const date = new Date(book.createdAt).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' });

          return (
            <div key={book.id} className="group flex flex-col card-blur border border-card-border rounded-[32px] overflow-hidden hover:shadow-xl transition-all">
              <div className="h-48 bg-stone-100 dark:bg-stone-900 flex items-center justify-center relative cursor-pointer"
                onClick={() => onOpenBook(book.id)}>
                <Book size={64} className="text-stone-300 opacity-40 group-hover:scale-110 transition-transform" />
                <div className="absolute top-6 left-6 px-3 py-1 bg-white/80 dark:bg-dark-surface/80 rounded-full text-[9px] uppercase font-black tracking-tighter">
                  {progressPct}%
                </div>
                {book.isStreaming && (
                  <div className="absolute top-6 right-6 px-3 py-1 bg-dusty-blue/10 border border-dusty-blue/20 rounded-full flex items-center gap-1.5">
                    <Loader2 size={10} className="text-dusty-blue animate-spin" />
                    <span className="text-[8px] font-bold text-dusty-blue uppercase">Translating</span>
                  </div>
                )}
              </div>
              <div className="p-8 space-y-4 text-left">
                <div>
                  <h4 className="text-xl font-serif text-charcoal dark:text-white">{book.title}</h4>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
                    <div className="h-full bg-sage rounded-full transition-all" style={{ width: `${progressPct}%` }} />
                  </div>
                  <span className="text-[10px] font-bold text-sage">{completedCount}/{book.totalChapters}</span>
                </div>
                <div className="pt-4 border-t border-stone-100 dark:border-stone-800 flex items-center justify-between">
                  <span className="text-xs text-warm-gray">{date}</span>
                  <div className="flex items-center gap-2">
                    <button onClick={() => onOpenBook(book.id)}
                      className="px-3 py-1.5 rounded-xl bg-charcoal text-white text-[9px] font-bold uppercase tracking-widest hover:bg-dusty-blue transition-all">
                      {t.openBook}
                    </button>
                    <button onClick={() => onRemoveBook(book.id)}
                      className="p-1.5 rounded-xl text-stone-300 hover:text-rose-500 hover:bg-rose-50 transition-colors">
                      <X size={14} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// --- Quick Translate View ---

const QuickTranslateView = ({ lang, playActionSound }: { lang: Language, playActionSound: (t: 'click') => void }) => {
  const [appState, setAppState] = useState<'idle' | 'translating' | 'completed' | 'error'>('idle');
  const [inputText, setInputText] = useState('');
  const [outputText, setOutputText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const t = UI_STRINGS[lang];

  const startTranslation = async () => {
    playActionSound('click');
    if (!inputText.trim()) return;
    setAppState('translating');
    setOutputText('');
    setErrorMsg('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/chapters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Quick Translate',
          source_text: inputText,
        }),
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data = await response.json();
      if (data.error) throw new Error(data.error);
      const text = data.final_text || (data.segments?.[0]?.final_text) || '(empty response)';
      setOutputText(text);
      setAppState('completed');
    } catch (err: any) {
      setErrorMsg(err.message || 'Translation failed');
      setAppState('error');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-12 animate-in fade-in duration-700">
      <header className="text-center space-y-4">
        <h2 className="text-3xl font-serif text-charcoal dark:text-white">Quick Studio</h2>
        <p className="text-sm text-warm-gray max-w-lg mx-auto">Fast raw extraction for high-density reading.</p>
      </header>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-[500px]">
        <Panel title="Input" icon={Play}>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Paste text..."
            className="w-full h-48 bg-stone-50 dark:bg-stone-900 border border-card-border rounded-xl p-4 text-sm focus:outline-none resize-none"
          />
          <button onClick={startTranslation} disabled={appState === 'translating' || !inputText.trim()}
            className={`w-full py-4 mt-6 rounded-xl font-bold uppercase tracking-widest text-[10px] transition-all ${
              appState === 'translating' || !inputText.trim()
                ? 'bg-stone-100 text-stone-300 cursor-not-allowed'
                : 'bg-charcoal text-white hover:bg-dusty-blue'
            }`}>
            {appState === 'translating' ? 'Translating...' : 'Execute'}
          </button>
        </Panel>
        <Panel title="Output" icon={Languages}>
          <div className="h-full flex items-center justify-center">
            {appState === 'idle' && <p className="font-serif italic text-warm-gray">Awaiting consciousness...</p>}
            {appState === 'translating' && <MistOverlay stages={stages} />}
            {appState === 'completed' && (
              <div className="w-full h-full overflow-y-auto">
                <p className="text-left font-serif leading-relaxed text-charcoal dark:text-[#cbd5e1] whitespace-pre-wrap">{outputText}</p>
              </div>
            )}
            {appState === 'error' && (
              <div className="text-center">
                <p className="text-rose-500 text-xs font-bold mb-2">Translation Error</p>
                <p className="font-serif italic text-warm-gray text-sm">{errorMsg}</p>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
};


// --- Audio Component ---

const AudioSettingsMenu = ({ settings, setSettings, lang, playActionSound, containerRef }: { settings: AudioSettings; setSettings: (s: AudioSettings) => void; lang: Language; playActionSound: (type: 'click' | 'page') => void, containerRef: React.RefObject<HTMLDivElement> }) => {
  const t = UI_STRINGS[lang];
  const soundProfiles = [
    { name: lang === 'en' ? 'Click' : '咔嗒声', desc: 'Sharp Mec' },
    { name: lang === 'en' ? 'Bubble' : '水泡声', desc: 'Sine Sweep' },
    { name: lang === 'en' ? 'Paper' : '揉纸团声', desc: 'Textured' }
  ];

  return (
    <div ref={containerRef} className="absolute top-12 right-0 w-64 bg-white/90 dark:bg-dark-surface/90 backdrop-blur-xl border border-card-border rounded-3xl shadow-2xl p-6 z-[200] animate-in fade-in zoom-in-95 pointer-events-auto text-left">
      <h4 className="text-[10px] font-black uppercase tracking-widest text-charcoal dark:text-white mb-6 flex items-center gap-2"><Volume2 size={14} /> {t.audio}</h4>
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold text-warm-gray uppercase tracking-widest">{t.clicks}</span>
          <button onClick={() => { const val = !settings.clicksEnabled; setSettings({...settings, clicksEnabled: val}); if (val) playActionSound('click'); }}
            className={`w-10 h-5 rounded-full relative transition-all ${settings.clicksEnabled ? 'bg-dusty-blue' : 'bg-stone-200 dark:bg-stone-800'}`}>
            <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${settings.clicksEnabled ? 'left-6' : 'left-1'}`} />
          </button>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold text-warm-gray uppercase tracking-widest">{t.pageTurn}</span>
          <button onClick={() => { const val = !settings.pageTurnEnabled; setSettings({...settings, pageTurnEnabled: val}); if (val) playActionSound('page'); }}
            className={`w-10 h-5 rounded-full relative transition-all ${settings.pageTurnEnabled ? 'bg-lavender' : 'bg-stone-200 dark:bg-stone-800'}`}>
            <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${settings.pageTurnEnabled ? 'left-6' : 'left-1'}`} />
          </button>
        </div>
        <div className="h-px bg-card-border opacity-50 my-2" />
        <div className="space-y-3">
          <span className="text-[9px] font-black text-stone-300 uppercase tracking-widest">{t.soundProfile}</span>
          <div className="grid grid-cols-1 gap-2">
            {soundProfiles.map((s, i) => (
              <button key={i} onClick={() => { setSettings({...settings, selectedSound: i}); playActionSound('click'); }}
                className={`p-3 rounded-xl border text-left transition-all ${settings.selectedSound === i ? 'border-dusty-blue bg-dusty-blue/5 text-dusty-blue' : 'border-card-border text-warm-gray'}`}>
                <p className="text-[10px] font-bold leading-none">{s.name}</p>
                <p className="text-[8px] opacity-60 font-mono mt-1">{s.desc}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// --- Main App ---

export default function App() {
  const [view, setView] = useState<AppView>('library');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [lang, setLang] = useState<Language>('en');
  const [audioSettings, setAudioSettings] = useState<AudioSettings>({ clicksEnabled: true, pageTurnEnabled: true, selectedSound: 0 });
  const [showAudioMenu, setShowAudioMenu] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [readerConfig, setReaderConfig] = useState<ReaderConfig>({ fontSize: 18, lineSpacing: 'relaxed', isBilingual: false });
  const [showInspector, setShowInspector] = useState(false);
  const [libraryBooks, setLibraryBooks] = useState<Book[]>([]);
  const [currentBook, setCurrentBook] = useState<Book | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const audioMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (audioMenuRef.current && !audioMenuRef.current.contains(event.target as Node)) setShowAudioMenu(false);
    };
    if (showAudioMenu) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showAudioMenu]);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const playSound = useCallback((type: 'click' | 'page', force?: boolean) => {
    if (!force && type === 'click' && !audioSettings.clicksEnabled) return;
    if (!force && type === 'page' && !audioSettings.pageTurnEnabled) return;
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      if (type === 'click') {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        if (audioSettings.selectedSound === 0) {
          osc.frequency.setValueAtTime(1200, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.05);
          osc.type = 'triangle';
          gain.gain.setValueAtTime(0.015, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);
        } else if (audioSettings.selectedSound === 1) {
          osc.frequency.setValueAtTime(400, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.1);
          osc.type = 'sine';
          gain.gain.setValueAtTime(0.02, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
        } else {
          const bufferSize = 2 * ctx.sampleRate, noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate), output = noiseBuffer.getChannelData(0);
          for (let i = 0; i < bufferSize; i++) output[i] = Math.random() * 2 - 1;
          const whiteNoise = ctx.createBufferSource(); whiteNoise.buffer = noiseBuffer;
          const lowpass = ctx.createBiquadFilter(); lowpass.type = 'lowpass'; lowpass.frequency.value = 1000;
          whiteNoise.connect(lowpass); lowpass.connect(gain);
          gain.gain.setValueAtTime(0.01, ctx.currentTime);
          gain.gain.linearRampToValueAtTime(0.001, ctx.currentTime + 0.15);
          whiteNoise.start(); whiteNoise.stop(ctx.currentTime + 0.15);
          gain.connect(ctx.destination); return;
        }
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + 0.1);
      } else {
        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
        const osc = ctx.createOscillator();
        osc.frequency.setValueAtTime(180, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(50, ctx.currentTime + 0.3);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(); osc.stop(ctx.currentTime + 0.3);
      }
    } catch (e) { }
  }, [audioSettings]);

  useEffect(() => {
    if (theme === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
  }, [theme]);

  const toggleTheme = () => { playSound('click'); setTheme(prev => prev === 'light' ? 'dark' : 'light'); };

  const mergeBook = useCallback((book: Book) => {
    setCurrentBook(prev => prev?.id === book.id ? book : prev);
    setLibraryBooks(prev => {
      const existing = prev.find(b => b.id === book.id);
      if (!existing) return [...prev, book];
      return prev.map(b => b.id === book.id ? book : b);
    });
  }, []);

  const fetchBookDetail = useCallback(async (bookId: string, previous?: Book): Promise<Book> => {
    const response = await fetch(`${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}`);
    if (!response.ok) throw new Error(await readApiError(response));
    const detail: BookDetailResponse = await response.json();
    return mapBookDetail(detail, previous);
  }, []);

  const loadChapterContent = useCallback(async (bookId: string, index: number): Promise<ChapterContentResponse> => {
    const response = await fetch(`${API_BASE_URL}/api/books/${encodeURIComponent(bookId)}/chapters/${index}`);
    if (!response.ok) throw new Error(await readApiError(response));
    const chapter: ChapterContentResponse = await response.json();

    setCurrentBook(prev => prev?.id === bookId ? applyChapterContent(prev, chapter) : prev);
    setLibraryBooks(prev => prev.map(book => book.id === bookId ? applyChapterContent(book, chapter) : book));
    return chapter;
  }, []);

  const ensureChapterLoaded = useCallback((index: number) => {
    const book = currentBook;
    const chapter = book?.chapters.find(ch => ch.index === index);
    if (!book || !chapter || chapter.sourceText) return;
    loadChapterContent(book.id, index).catch(err => console.error('Chapter load error:', err));
  }, [currentBook, loadChapterContent]);

  const startBookTranslation = useCallback((initialBook: Book) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const abortController = new AbortController();
    abortRef.current = abortController;

    (async () => {
      let latestBook = initialBook;
      try {
        while (true) {
          if (abortController.signal.aborted) return;
          const next = latestBook.chapters.find(ch => ch.status === 'pending');
          if (next) {
            latestBook = {
              ...latestBook,
              isStreaming: true,
              chapters: latestBook.chapters.map(ch => ch.index === next.index ? { ...ch, status: 'translating' } : ch),
            };
            mergeBook(latestBook);
          }

          const response = await fetch(`${API_BASE_URL}/api/books/${encodeURIComponent(latestBook.id)}/translate-next`, {
            method: 'POST',
            signal: abortController.signal,
          });
          if (!response.ok) throw new Error(await readApiError(response));

          const result: TranslateNextResponse = await response.json();
          latestBook = mapBookDetail(result.book, latestBook);
          mergeBook(latestBook);

          if (result.ran_index === null) {
            latestBook = { ...latestBook, isStreaming: false };
            mergeBook(latestBook);
            break;
          }

          const chapter = await loadChapterContent(result.book_id, result.ran_index);
          latestBook = applyChapterContent(latestBook, chapter);
          if (!result.success) break;
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return;
        console.error('Book translation error:', err);
        mergeBook({
          ...latestBook,
          chapters: latestBook.chapters.map(ch =>
            ch.status === 'translating' ? { ...ch, status: 'error', error: err.message || 'Translation failed' } : ch
          ),
          isStreaming: false,
        });
      }
    })();
  }, [loadChapterContent, mergeBook]);

  const handleUpload = async (_title: string, _author: string, file: UploadedFile) => {
    if (abortRef.current) abortRef.current.abort();
    const formData = new FormData();
    formData.append('file', file.file, file.name);

    try {
      const uploadResponse = await fetch(`${API_BASE_URL}/api/books`, {
        method: 'POST',
        body: formData,
      });
      if (!uploadResponse.ok) throw new Error(await readApiError(uploadResponse));
      const uploaded: BookDetailResponse = await uploadResponse.json();
      const hydratedBook = await fetchBookDetail(uploaded.book.book_id);

      mergeBook(hydratedBook);
      setCurrentBook(hydratedBook);
      setView('reader');
      setShowUploadModal(false);
      if (hydratedBook.chapters[0]) {
        loadChapterContent(hydratedBook.id, hydratedBook.chapters[0].index).catch(err => console.error('Chapter load error:', err));
      }
      startBookTranslation(hydratedBook);
    } catch (err) {
      console.error('Book upload error:', err);
    }
  };

  const openBookReader = async (bookId: string) => {
    const book = libraryBooks.find(b => b.id === bookId);
    if (book) {
      setCurrentBook(book);
      setView('reader');
      try {
        const freshBook = await fetchBookDetail(bookId, book);
        mergeBook(freshBook);
        setCurrentBook(freshBook);
      } catch (err) {
        console.error('Book detail refresh error:', err);
      }
    }
  };

  const removeBook = (bookId: string) => {
    if (window.confirm("Remove this book from library?")) {
      setLibraryBooks(prev => prev.filter(b => b.id !== bookId));
      if (currentBook?.id === bookId) {
        setCurrentBook(null);
        setView('library');
      }
    }
  };

  const closeReader = () => {
    playSound('click');
    // Ensure the current book is saved to library before leaving the reader.
    setLibraryBooks(prev => {
      if (!currentBook) return prev;
      if (prev.some(b => b.id === currentBook.id)) return prev;
      return [...prev, currentBook];
    });
    setView('library');
  };

  const navItems: { id: AppView; label: string; icon: any }[] = [
    { id: 'library', label: UI_STRINGS[lang].library, icon: Book },
    { id: 'quick-translate', label: UI_STRINGS[lang].quickTranslate, icon: Zap },
    { id: 'profile', label: UI_STRINGS[lang].profile, icon: ShieldCheck }
  ];

  const t = UI_STRINGS[lang];

  return (
    <div className={`min-h-screen transition-colors duration-500 overflow-x-hidden ${view === 'reader' ? (isFullscreen ? 'p-0' : 'p-4 md:p-6') : 'p-8 md:p-12 pb-20'} ${theme === 'dark' ? 'bg-dark-bg text-dark-text' : 'bg-bg-ivory text-charcoal'}`}>
      <header className={`max-w-[1600px] w-full mx-auto flex flex-col ${view === 'reader' ? (isFullscreen ? 'px-0' : '') : 'mb-10 gap-8 px-4'}`}>
        {view !== 'reader' && (
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pointer-events-none sticky top-0 z-[100]">
            <div className="pointer-events-auto">
              <div className="flex items-center gap-4 mb-2">
                <h1 className="text-2xl md:text-3xl font-serif font-light tracking-tight text-charcoal dark:text-white">Novel Translation Workbench</h1>
                <StatusPill>{t.statusPill}</StatusPill>
              </div>
              <p className="text-warm-gray text-sm font-medium tracking-wide text-left uppercase">Version 1.0.5 • Atlas Chassis</p>
            </div>
            <div className="flex items-center gap-4 pointer-events-auto relative">
              <div className="relative">
                <motion.button onClick={() => { playSound('click'); setShowAudioMenu(!showAudioMenu); }} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                  className={`w-10 h-10 rounded-full border flex items-center justify-center transition-all ${showAudioMenu ? 'bg-dusty-blue text-white border-dusty-blue' : 'bg-white dark:bg-dark-surface border-card-border text-warm-gray'}`}
                ><Volume2 size={18} /></motion.button>
                {showAudioMenu && <AudioSettingsMenu settings={audioSettings} setSettings={setAudioSettings} lang={lang} playActionSound={(t) => playSound(t, true)} containerRef={audioMenuRef} />}
              </div>
              <div className="h-6 w-[1px] bg-card-border mx-2" />
              <motion.button onClick={toggleTheme} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                className={`w-10 h-10 rounded-full border flex items-center justify-center transition-all ${theme === 'dark' ? 'bg-dark-surface border-dark-border text-lavender' : 'bg-white border-card-border text-warm-gray'}`}
              ><Settings2 size={18} /></motion.button>
            </div>
          </div>
        )}
        {view !== 'reader' && (
          <nav className="flex items-center gap-10 border-b border-card-border overflow-x-auto no-scrollbar pt-4">
            {navItems.map((item) => (
              <button key={item.id} onClick={() => { playSound('click'); setView(item.id); }}
                className={`pb-4 text-[10px] font-black uppercase tracking-[0.25em] transition-all relative flex items-center gap-2.5 whitespace-nowrap ${view === item.id ? 'text-charcoal dark:text-white' : 'text-warm-gray hover:text-charcoal'}`}
              >
                <item.icon size={13} className={view === item.id ? 'text-dusty-blue' : ''} /> {item.label}
                {view === item.id && <motion.div layoutId="nav-pill" className="absolute bottom-0 left-0 right-0 h-1 bg-dusty-blue rounded-t-full" />}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-3">
              <motion.button
                onClick={() => { playSound('click'); setShowUploadModal(true); }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="px-5 py-2.5 rounded-xl bg-charcoal text-white text-[10px] font-black uppercase tracking-widest shadow-lg hover:bg-dusty-blue transition-all flex items-center gap-2"
              >
                <Play size={12} fill="currentColor" /> {t.newBook}
              </motion.button>
            </div>
          </nav>
        )}
      </header>

      <main className={`flex-1 w-full mx-auto ${isFullscreen ? 'max-w-none px-0' : 'max-w-[1600px] px-4'}`}>
        {view === 'reader' && currentBook ? (
          <BookReaderView
            book={currentBook}
            lang={lang}
            readerConfig={readerConfig}
            setReaderConfig={setReaderConfig}
            showInspector={showInspector}
            setShowInspector={setShowInspector}
            audioSettings={audioSettings}
            playActionSound={playSound}
            onBack={closeReader}
            onLoadChapter={ensureChapterLoaded}
            isFullscreen={isFullscreen}
          />
        ) : view === 'library' ? (
          <LibraryView books={libraryBooks} onOpenBook={openBookReader} onRemoveBook={removeBook} lang={lang} />
        ) : view === 'quick-translate' ? (
          <QuickTranslateView lang={lang} playActionSound={playSound} />
        ) : view === 'profile' ? (
          <ProfileView />
        ) : null}
      </main>

      {view !== 'reader' && (
        <footer className="max-w-[1600px] w-full mx-auto mt-20 border-t border-card-border/30 pt-10 px-4 flex justify-between text-[10px] font-bold uppercase tracking-[0.3em] text-warm-gray/60">
          <div className="flex gap-8"><span>Project Atlas v1.0.5</span><span>System Integrity: Nominal</span></div>
          <div>sys: debug_chassis</div>
        </footer>
      )}

      <AnimatePresence>
        {showUploadModal && (
          <UploadModal lang={lang} onUpload={handleUpload} onCancel={() => { playSound('click'); setShowUploadModal(false); }} playActionSound={playSound} />
        )}
      </AnimatePresence>
    </div>
  );
}

// --- Profile View ---

function ProfileView() {
  return (
    <div className="max-w-4xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700 pb-20">
      <div className="card-blur border border-card-border rounded-[40px] overflow-hidden shadow-sm text-left">
        <div className="h-48 bg-charcoal relative"><div className="absolute inset-0 bg-gradient-to-r from-dusty-blue/20 to-lavender/20 blur-3xl opacity-50" /></div>
        <div className="px-12 pb-12 pt-16">
          <h2 className="text-3xl font-serif text-charcoal dark:text-white">Zhe Kou</h2>
          <p className="text-sm font-medium text-warm-gray mb-8">Lead Architect • Project Atlas</p>
          <p className="text-sm text-warm-gray leading-relaxed font-serif italic max-w-2xl">Focused on bridging complex LLM architectures with elegant editorial experiences. Dedicated to the craft of translation through human-centric AI design.</p>
          <div className="mt-12 grid grid-cols-2 gap-4">
            <div className="p-6 rounded-3xl bg-sage/5 border border-sage/10 text-[10px] uppercase font-black tracking-widest text-sage">System Authority granted</div>
            <div className="p-6 rounded-3xl bg-lavender/5 border border-lavender/10 text-[10px] uppercase font-black tracking-widest text-lavender">Local Identity verified</div>
          </div>
        </div>
      </div>
    </div>
  );
}
