import { useState } from 'react';
import type { Book } from '../types';
import { useBooks } from '../hooks/useBooks';
import ImportDialog from './ImportDialog';

interface Props {
  onOpenBook: (book: Book) => void;
}

export default function Library({ onOpenBook }: Props) {
  const { books, addBook } = useBooks();
  const [showImport, setShowImport] = useState(false);
  const [search, setSearch] = useState('');
  const [showSearch, setShowSearch] = useState(false);

  const filtered = books.filter(b =>
    b.title.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="h-full bg-bg-ivory flex flex-col">
      {/* Header */}
      <header className="text-center py-5 border-b border-card-border">
        <h1 className="text-lg font-semibold text-charcoal tracking-wide">
          Novel Translation Workbench
        </h1>
      </header>

      <div className="flex-1 overflow-auto px-8 py-6">
        {/* Library header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-charcoal">My Library</h2>
            <span className="text-xs bg-[#eae6db] text-warm-gray px-2 py-0.5 rounded-full">
              {books.length} {books.length === 1 ? 'book' : 'books'}
            </span>
          </div>
          <div className="flex items-center gap-3 text-warm-gray">
            <button
              onClick={() => setShowSearch(s => !s)}
              className="text-sm hover:text-charcoal cursor-pointer"
            >
              🔍
            </button>
            <button
              onClick={() => setShowImport(true)}
              className="px-3 py-1.5 text-sm bg-charcoal text-bg-ivory rounded-md hover:opacity-90 cursor-pointer"
            >
              + Import
            </button>
          </div>
        </div>

        {/* Search (expandable) */}
        {showSearch && (
          <input
            autoFocus
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search books..."
            className="w-full mb-4 px-3 py-1.5 text-sm border border-card-border rounded-md bg-bg-ivory text-charcoal outline-none focus:border-amber"
          />
        )}

        {/* Book grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5">
          {filtered.map(book => (
            <button
              key={book.id}
              onClick={() => onOpenBook(book)}
              className="aspect-[3/4] bg-[#eae6db] rounded-lg p-3 flex flex-col justify-end text-left hover:opacity-80 transition-opacity cursor-pointer"
            >
              <div className="font-semibold text-sm text-charcoal">{book.title}</div>
              <div className="text-xs text-warm-gray mt-1">
                {book.currentChapter > 0
                  ? `Continue ▸ Ch.${book.currentChapter}`
                  : book.status === 'translated'
                    ? 'Read now'
                    : book.status === 'translating'
                      ? 'Translating...'
                      : 'Not translated'}
              </div>
            </button>
          ))}

          {/* Import card */}
          <button
            onClick={() => setShowImport(true)}
            className="aspect-[3/4] border-2 border-dashed border-[#d0c4ae] rounded-lg flex items-center justify-center text-[#a6927a] hover:border-warm-gray transition-colors cursor-pointer"
          >
            <span className="text-2xl">+</span>
          </button>
        </div>

        {filtered.length === 0 && books.length > 0 && (
          <p className="text-center text-warm-gray text-sm mt-12">No books match your search.</p>
        )}

        {books.length === 0 && (
          <div className="text-center mt-24">
            <p className="text-warm-gray mb-4">Your library is empty.</p>
            <button
              onClick={() => setShowImport(true)}
              className="px-4 py-2 bg-charcoal text-bg-ivory rounded-md text-sm cursor-pointer"
            >
              Import your first book
            </button>
          </div>
        )}
      </div>

      {showImport && (
        <ImportDialog
          onClose={() => setShowImport(false)}
          onImport={book => {
            addBook(book);
            setShowImport(false);
          }}
        />
      )}
    </div>
  );
}
