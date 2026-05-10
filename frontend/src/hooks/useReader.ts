import { useState, useCallback } from 'react';
import type { Highlight, Book } from '../types';

const HIGHLIGHT_KEY = 'ntw_highlights';

function loadHighlights(bookId: string): Highlight[] {
  try {
    const raw = localStorage.getItem(`${HIGHLIGHT_KEY}_${bookId}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function useReader(book: Book) {
  const [highlights, setHighlights] = useState<Highlight[]>(() => loadHighlights(book.id));
  const [selectedText, setSelectedText] = useState<{ text: string } | null>(null);

  const saveHighlight = useCallback((chapterIndex: number, text: string) => {
    setHighlights(prev => {
      const h: Highlight = {
        id: Date.now().toString(36),
        chapterIndex,
        text,
        note: '',
        createdAt: Date.now(),
      };
      const updated = [...prev, h];
      localStorage.setItem(`${HIGHLIGHT_KEY}_${book.id}`, JSON.stringify(updated));
      return updated;
    });
  }, [book.id]);

  const removeHighlight = useCallback((id: string) => {
    setHighlights(prev => {
      const updated = prev.filter(h => h.id !== id);
      localStorage.setItem(`${HIGHLIGHT_KEY}_${book.id}`, JSON.stringify(updated));
      return updated;
    });
  }, [book.id]);

  const handleTextSelection = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return;
    const text = sel.toString().trim();
    if (!text) return;

    // Only allow if selection is within reader content
    const readerEl = document.querySelector('[data-reader-content]');
    if (readerEl && readerEl.contains(sel.anchorNode)) {
      setSelectedText({ text: text });
    }
  }, []);

  return {
    highlights,
    selectedText,
    setSelectedText,
    saveHighlight,
    removeHighlight,
    handleTextSelection,
  };
}
