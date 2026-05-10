import type { Chapter } from '../types';

interface Props {
  title: string;
  chapters: Chapter[];
  onTranslateAll: () => void;
}

export default function ChapterPreview({ title, chapters, onTranslateAll }: Props) {
  const readyCount = chapters.filter(c => c.status === 'ready').length;
  const doneCount = chapters.filter(c => c.status === 'done').length;

  return (
    <div className="bg-bg-ivory rounded-lg overflow-hidden border border-card-border">
      <div className="flex items-center justify-between px-5 py-4 border-b border-card-border">
        <div>
          <h3 className="font-semibold text-charcoal">{title}</h3>
          <p className="text-xs text-warm-gray mt-0.5">
            {chapters.length} {chapters.length === 1 ? 'chapter' : 'chapters'}
          </p>
        </div>
      </div>

      <div className="divide-y divide-card-border">
        {chapters.map(ch => (
          <div key={ch.index} className="flex items-center justify-between px-5 py-2.5">
            <span className="text-sm text-charcoal">
              {ch.index + 1}. {ch.title}
            </span>
            <span className={`text-xs ${
              ch.status === 'done' ? 'text-sage' :
              ch.status === 'translating' ? 'text-amber' :
              ch.status === 'error' ? 'text-red-400' :
              'text-warm-gray'
            }`}>
              {ch.status === 'ready' ? '● Ready' :
               ch.status === 'done' ? '✓ Done' :
               ch.status === 'translating' ? '⟳ Translating' :
               '✗ Error'}
            </span>
          </div>
        ))}
      </div>

      {readyCount > 0 && (
        <div className="px-5 py-3 border-t border-card-border flex justify-end">
          <button
            onClick={onTranslateAll}
            className="px-4 py-2 text-sm bg-charcoal text-bg-ivory rounded-md cursor-pointer hover:opacity-90"
          >
            Translate All ({readyCount})
          </button>
        </div>
      )}

      {doneCount === chapters.length && chapters.length > 0 && (
        <div className="px-5 py-3 border-t border-card-border text-center text-sm text-sage">
          ✓ All chapters translated
        </div>
      )}
    </div>
  );
}
