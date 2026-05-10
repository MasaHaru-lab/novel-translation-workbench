import type { Chapter } from '../types';

interface Props {
  chapters: Chapter[];
  currentIndex: number;
  onCancel: () => void;
}

export default function TranslationProgress({ chapters, currentIndex, onCancel }: Props) {
  const done = chapters.filter(c => c.status === 'done').length;
  const total = chapters.length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="bg-bg-ivory rounded-lg border border-card-border p-5">
      <h3 className="font-semibold text-charcoal mb-3">
        Translating — Chapter {currentIndex + 1} of {total}
      </h3>

      {/* Progress bar */}
      <div className="h-1.5 bg-[#eae6db] rounded-full mb-4 overflow-hidden">
        <div
          className="h-full bg-sage rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Chapter list */}
      <div className="space-y-1 text-sm">
        {chapters.map((ch, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className={
              ch.status === 'done' ? 'text-sage' :
              ch.status === 'translating' ? 'text-amber' :
              ch.status === 'error' ? 'text-red-400' :
              'text-warm-gray'
            }>
              {ch.status === 'done' ? '✓' :
               ch.status === 'translating' ? '⟳' :
               ch.status === 'error' ? '✗' :
               '○'}
            </span>
            <span className={
              ch.status === 'done' ? 'text-charcoal' : 'text-warm-gray'
            }>
              {ch.title}
            </span>
            {ch.status === 'error' && (
              <span className="text-xs text-red-400">Failed</span>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={onCancel}
        className="mt-4 text-sm text-warm-gray hover:text-charcoal cursor-pointer"
      >
        Cancel
      </button>
    </div>
  );
}
