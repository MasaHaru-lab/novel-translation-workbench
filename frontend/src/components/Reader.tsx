import { useState, useMemo } from 'react';
import type { Book, ReaderSettings } from '../types';
import ReaderSettingsPopover from './ReaderSettings';
import { useReader } from '../hooks/useReader';

interface Props {
  book: Book;
  settings: ReaderSettings;
  onSettingsChange: (s: ReaderSettings) => void;
  onClose: () => void;
}

// Split chapter content into pages (roughly 20 lines per page in dual mode)
function paginate(text: string, linesPerPage: number = 20): string[] {
  const lines = text.split('\n').filter(l => l.trim());
  const pages: string[] = [];
  for (let i = 0; i < lines.length; i += linesPerPage) {
    pages.push(lines.slice(i, i + linesPerPage).join('\n'));
  }
  return pages.length > 0 ? pages : [''];
}

export default function Reader({ book, settings, onSettingsChange, onClose }: Props) {
  const [chapterIndex, setChapterIndex] = useState(book.currentChapter);
  const [pageIndex, setPageIndex] = useState(0);
  const [showSettings, setShowSettings] = useState(false);

  const chapter = book.chapters[chapterIndex];
  const pages = useMemo(() => paginate(chapter?.content || '', 20), [chapter]);
  const totalPages = pages.length;

  const { highlights, selectedText, setSelectedText, saveHighlight, handleTextSelection } = useReader(book);

  const goNext = () => {
    if (pageIndex < totalPages - 1) {
      setPageIndex(p => p + 1);
    } else if (chapterIndex < book.chapters.length - 1) {
      setChapterIndex(i => i + 1);
      setPageIndex(0);
    }
  };

  const goPrev = () => {
    if (pageIndex > 0) {
      setPageIndex(p => p - 1);
    } else if (chapterIndex > 0) {
      setChapterIndex(i => i - 1);
      setPageIndex(0);
    }
  };

  // Split pages into left/right for dual-page
  const leftPage = pages[pageIndex] || '';
  const rightPage = pageIndex + 1 < totalPages ? pages[pageIndex + 1] : '';

  const isDualPage = totalPages > 1 && window.innerWidth >= 900;

  // Helper: render text with highlight marks
  const renderContent = (text: string) => {
    const chapterHighlights = highlights.filter(h => h.chapterIndex === chapterIndex);
    return text.split('\n').map((line, i) => {
      const isHighlighted = chapterHighlights.some(h => h.text === line.trim());
      return (
        <p key={i} className={`mb-3 indent-8 ${isHighlighted ? 'bg-[#e6d8bd] dark:bg-[rgba(212,163,115,0.2)] -mx-1 px-1 rounded' : ''}`}>
          {line || ' '}
        </p>
      );
    });
  };

  return (
    <div className={`h-full flex flex-col ${settings.theme === 'dark' ? 'dark' : ''}`}>
      <div className={
        settings.theme === 'dark'
          ? 'h-full flex flex-col bg-dark-bg'
          : 'h-full flex flex-col bg-bg-ivory'
      }>
        {/* Top bar */}
        <header className={`flex items-center justify-between px-4 py-2 text-sm border-b shrink-0 ${
          settings.theme === 'dark'
            ? 'border-dark-border text-dark-text'
            : 'border-card-border text-charcoal'
        }`}>
          <button onClick={onClose} className={`text-xs cursor-pointer ${
            settings.theme === 'dark' ? 'text-dark-subtext hover:text-dark-text' : 'text-warm-gray hover:text-charcoal'
          }`}>
            ← Library
          </button>
          <div className={`text-xs ${settings.theme === 'dark' ? 'text-dark-text' : 'text-charcoal'}`}>
            {book.title} · {chapter?.title || `Chapter ${chapterIndex + 1}`}
          </div>
          <button onClick={onClose} className={`text-xs cursor-pointer ${
            settings.theme === 'dark' ? 'text-dark-subtext hover:text-dark-text' : 'text-warm-gray hover:text-charcoal'
          }`}>
            ✕
          </button>
        </header>

        {/* Reading area */}
        <div className="flex-1 flex overflow-hidden">
          {isDualPage ? (
            /* Dual-page spread */
            <>
              <div className={`flex-1 overflow-auto p-8 lg:p-10 xl:p-12 border-r ${
                settings.theme === 'dark' ? 'border-dark-border' : 'border-card-border'
              }`}>
                <div
                  data-reader-content
                  onMouseUp={handleTextSelection}
                  className="leading-relaxed text-justify select-text"
                  style={{
                    fontSize: `${settings.fontSize}px`,
                    fontFamily: 'Georgia, serif',
                    color: settings.theme === 'dark' ? '#fef3c7' : '#2D2D2D',
                  }}
                >
                  {renderContent(leftPage)}
                </div>
              </div>
              <div className={`flex-1 overflow-auto p-8 lg:p-10 xl:p-12 ${
                settings.theme === 'dark' ? 'border-dark-border' : 'border-card-border'
              }`}>
                <div
                  data-reader-content
                  onMouseUp={handleTextSelection}
                  className="leading-relaxed text-justify select-text"
                  style={{
                    fontSize: `${settings.fontSize}px`,
                    fontFamily: 'Georgia, serif',
                    color: settings.theme === 'dark' ? '#fef3c7' : '#2D2D2D',
                  }}
                >
                  {rightPage ? renderContent(rightPage) : ''}
                </div>
              </div>
            </>
          ) : (
            /* Single page for mobile/tablet */
            <div className="flex-1 overflow-auto p-6 md:p-8">
              <div
                data-reader-content
                onMouseUp={handleTextSelection}
                className="leading-relaxed text-justify select-text max-w-2xl mx-auto"
                style={{
                  fontSize: `${settings.fontSize}px`,
                  fontFamily: 'Georgia, serif',
                  color: settings.theme === 'dark' ? '#fef3c7' : '#2D2D2D',
                }}
              >
                {pages.map((pg, i) => (
                  <div key={i} className={i === pageIndex ? '' : 'hidden'}>
                    {renderContent(pg)}
                    <p className={`text-center text-sm mt-12 ${
                      settings.theme === 'dark' ? 'text-dark-subtext' : 'text-warm-gray'
                    }`}>— {pageIndex + 1} —</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Bottom bar */}
        <footer className={`flex items-center justify-between px-4 py-2 text-xs border-t shrink-0 ${
          settings.theme === 'dark'
            ? 'border-dark-border text-dark-subtext'
            : 'border-card-border text-warm-gray'
        }`}>
          <button onClick={goPrev} className="cursor-pointer hover:text-charcoal">← Prev</button>
          <div className="flex items-center gap-4">
            {isDualPage && (
              <span className="text-warm-gray">
                — {pageIndex + 1} — {rightPage ? `— ${pageIndex + 2} —` : ''}
              </span>
            )}
            {!isDualPage && (
              <span>— {pageIndex + 1} —</span>
            )}
            {!isDualPage && (
              <span>{Math.round(((chapterIndex * 30 + pageIndex) / (book.chapters.length * 30)) * 100)}%</span>
            )}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="cursor-pointer hover:text-charcoal"
            >
              Aa
            </button>
          </div>
          <button onClick={goNext} className="cursor-pointer hover:text-charcoal">Next →</button>
        </footer>

        {/* Highlight toolbar */}
        {selectedText && (
          <div className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 flex gap-2 px-4 py-2 rounded-lg shadow-lg border ${
            settings.theme === 'dark'
              ? 'bg-dark-surface border-dark-border'
              : 'bg-bg-ivory border-card-border'
          }`}>
            <button
              onClick={() => {
                saveHighlight(chapterIndex, selectedText.text);
                setSelectedText(null);
                window.getSelection()?.removeAllRanges();
              }}
              className="px-3 py-1.5 text-sm bg-amber text-charcoal rounded-md cursor-pointer hover:opacity-90"
            >
              🖊 Highlight
            </button>
            <button
              onClick={() => {
                setSelectedText(null);
                window.getSelection()?.removeAllRanges();
              }}
              className="px-3 py-1.5 text-sm text-warm-gray cursor-pointer hover:text-charcoal"
            >
              Cancel
            </button>
          </div>
        )}

        {/* Settings popover */}
        {showSettings && (
          <ReaderSettingsPopover
            settings={settings}
            onChange={onSettingsChange}
            onClose={() => setShowSettings(false)}
            theme={settings.theme}
          />
        )}
      </div>
    </div>
  );
}
