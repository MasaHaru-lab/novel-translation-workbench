// frontend/src/hooks/useBooks.ts
import { useState, useCallback } from 'react';
import type { Book } from '../types';

const STORAGE_KEY = 'ntw_books';

function loadBooks(): Book[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function useBooks() {
  const [books, setBooks] = useState<Book[]>(loadBooks);

  const addBook = useCallback((book: Book) => {
    setBooks(prev => {
      const updated = [...prev, book];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const updateBook = useCallback((id: string, updates: Partial<Book>) => {
    setBooks(prev => {
      const updated = prev.map(b => b.id === id ? { ...b, ...updates } : b);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  const removeBook = useCallback((id: string) => {
    setBooks(prev => {
      const updated = prev.filter(b => b.id !== id);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      return updated;
    });
  }, []);

  return { books, addBook, updateBook, removeBook };
}
