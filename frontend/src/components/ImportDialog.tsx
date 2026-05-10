import { useState } from 'react';
import type { Book, SourceType } from '../types';
import { createBookFromSource } from '../utils/contentParser';

interface Props {
  onClose: () => void;
  onImport: (book: Book) => void;
}

export default function ImportDialog({ onClose, onImport }: Props) {
  const [tab, setTab] = useState<SourceType>('file');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const name = file.name.replace(/\.(txt|md)$/i, '');
    setTitle(name);

    const text = await file.text();
    const book = createBookFromSource(name, file.name, 'file', text);
    onImport(book);
  };

  const handleUrl = async () => {
    if (!url.trim()) { setError('Please enter a URL'); return; }
    setError('');

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const html = await res.text();

      // Basic HTML title extraction
      const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i);
      const pageTitle = titleMatch?.[1]?.trim() || url.split('/').pop() || 'Untitled';

      // Strip HTML tags for plain text
      const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
      const book = createBookFromSource(pageTitle, url, 'web', text);
      onImport(book);
    } catch (err) {
      setError(`Could not fetch content: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
      <div className="bg-bg-ivory rounded-lg w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-card-border">
          <h3 className="font-semibold text-charcoal">Import Book</h3>
          <button onClick={onClose} className="text-warm-gray hover:text-charcoal cursor-pointer">✕</button>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b border-card-border">
          <button
            onClick={() => setTab('file')}
            className={`flex-1 py-2.5 text-sm font-medium text-center cursor-pointer ${
              tab === 'file'
                ? 'text-charcoal border-b-2 border-charcoal'
                : 'text-warm-gray hover:text-charcoal'
            }`}
          >
            Upload File
          </button>
          <button
            onClick={() => setTab('web')}
            className={`flex-1 py-2.5 text-sm font-medium text-center cursor-pointer ${
              tab === 'web'
                ? 'text-charcoal border-b-2 border-charcoal'
                : 'text-warm-gray hover:text-charcoal'
            }`}
          >
            Web Link
          </button>
        </div>

        <div className="p-5">
          {tab === 'file' ? (
            <label className="block border-2 border-dashed border-[#d0c4ae] rounded-lg p-8 text-center cursor-pointer hover:border-warm-gray transition-colors">
              <div className="text-2xl mb-2">📄</div>
              <div className="font-medium text-sm text-charcoal">Click to select file</div>
              <div className="text-xs text-warm-gray mt-1">.txt or .md</div>
              <input
                type="file"
                accept=".txt,.md"
                onChange={handleFile}
                className="hidden"
              />
            </label>
          ) : (
            <div>
              <input
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="Paste a web URL..."
                className="w-full px-3 py-2 text-sm border border-card-border rounded-md bg-bg-ivory text-charcoal outline-none focus:border-amber"
              />
              {error && <p className="text-red-500 text-xs mt-2">{error}</p>}
            </div>
          )}

          {/* Title */}
          <div className="mt-4">
            <label className="text-xs text-warm-gray mb-1 block">Book Title</label>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Auto-detected, editable"
              className="w-full px-3 py-2 text-sm border border-card-border rounded-md bg-bg-ivory text-charcoal outline-none focus:border-amber"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 mt-5">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-warm-gray border border-card-border rounded-md cursor-pointer hover:text-charcoal"
            >
              Cancel
            </button>
            {tab === 'web' && (
              <button
                onClick={handleUrl}
                className="px-4 py-2 text-sm bg-charcoal text-bg-ivory rounded-md cursor-pointer hover:opacity-90"
              >
                Import
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
