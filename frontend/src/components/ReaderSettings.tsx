import type { ReaderSettings, ThemeMode } from '../types';

interface Props {
  settings: ReaderSettings;
  onChange: (s: ReaderSettings) => void;
  onClose: () => void;
  theme: ThemeMode;
}

export default function ReaderSettingsPopover({ settings, onChange, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-40" onClick={onClose}>
      <div
        className={`absolute bottom-12 right-4 w-56 rounded-lg shadow-lg border p-4 ${
          settings.theme === 'dark'
            ? 'bg-dark-surface border-dark-border'
            : 'bg-bg-ivory border-card-border'
        }`}
        onClick={e => e.stopPropagation()}
      >
        <h4 className={`text-sm font-semibold mb-3 ${
          settings.theme === 'dark' ? 'text-dark-text' : 'text-charcoal'
        }`}>
          Reading Settings
        </h4>

        {/* Font size */}
        <label className={`text-xs mb-1 block ${
          settings.theme === 'dark' ? 'text-dark-subtext' : 'text-warm-gray'
        }`}>
          Font Size: {settings.fontSize}px
        </label>
        <input
          type="range"
          min="14"
          max="28"
          value={settings.fontSize}
          onChange={e => onChange({ ...settings, fontSize: Number(e.target.value) })}
          className="w-full mb-3 accent-amber"
        />

        {/* Theme toggle */}
        <div className="flex items-center justify-between">
          <span className={`text-xs ${
            settings.theme === 'dark' ? 'text-dark-subtext' : 'text-warm-gray'
          }`}>
            Dark Mode
          </span>
          <button
            onClick={() => onChange({
              ...settings,
              theme: settings.theme === 'dark' ? 'light' : 'dark',
            })}
            className={`w-10 h-5 rounded-full transition-colors relative ${
              settings.theme === 'dark' ? 'bg-amber' : 'bg-warm-gray'
            }`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
              settings.theme === 'dark' ? 'translate-x-5' : 'translate-x-0.5'
            }`} />
          </button>
        </div>
      </div>
    </div>
  );
}
