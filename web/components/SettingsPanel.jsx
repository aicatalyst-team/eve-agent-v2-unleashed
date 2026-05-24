import React, { useState, useEffect, useCallback } from 'react';

export function SettingsPanel({ isOpen, onClose }) {
  const [settings, setSettings] = useState({
    auto_accept_edits: false,
    plan_mode: false,
    max_loop_seconds: 120,
  });
  const [loading, setLoading] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  const [error, setError] = useState(null);

  // ── Load settings on mount ─────────────────────────────────
  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch('/settings');
      if (res.ok) {
        const data = await res.json();
        setSettings({
          auto_accept_edits: data.auto_accept_edits ?? false,
          plan_mode: data.plan_mode ?? false,
          max_loop_seconds: data.max_loop_seconds ?? 120,
        });
        console.log('✅ Settings loaded:', data);
      } else {
        throw new Error('Failed to load settings');
      }
    } catch (err) {
      console.error('❌ Error loading settings:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const saveSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const res = await fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        setLastSaved(new Date());
        console.log('✅ Settings saved:', data);
        
        // Broadcast to other tabs/windows
        localStorage.setItem('eve_settings_updated', JSON.stringify({
          timestamp: Date.now(),
          settings: data,
        }));
      } else {
        throw new Error('Failed to save settings');
      }
    } catch (err) {
      console.error('❌ Error saving settings:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [settings]);

  // ── Handle toggle changes ──────────────────────────────────
  const handleToggle = useCallback((key) => {
    setSettings(prev => {
      const updated = {
        ...prev,
        [key]: !prev[key],
      };
      // Auto-save when toggling
      setTimeout(() => {
        fetch('/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updated),
        })
          .then(res => res.json())
          .then(data => {
            console.log(`✅ Auto-saved ${key}:`, data[key]);
            setLastSaved(new Date());
          })
          .catch(err => console.error(`❌ Failed to save ${key}:`, err));
      }, 0);
      
      return updated;
    });
  }, []);

  const handleSliderChange = useCallback((key, value) => {
    setSettings(prev => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const handleSliderRelease = useCallback((key) => {
    // Save when user releases the slider
    fetch('/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    })
      .then(res => res.json())
      .then(data => {
        console.log(`✅ Saved ${key}:`, data[key]);
        setLastSaved(new Date());
      })
      .catch(err => console.error(`❌ Failed to save ${key}:`, err));
  }, [settings]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-800 border border-purple-500/20 shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <span className="text-2xl">⚙️</span>
            Agent Settings
          </h2>
          <button
            onClick={onClose}
            className="text-white/50 hover:text-white/80 transition-colors text-2xl leading-none"
          >
            ✕
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/25 text-[11px] text-red-400 font-mono">
            ⚠️ {error}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-4 text-white/40 text-sm">
            Updating settings...
          </div>
        )}

        <div className="space-y-5">
          {/* ── Auto-Accept Edits Toggle ──────────────────────────── */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-white/5 hover:border-purple-500/20 transition-all">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">📝</span>
                  <label className="text-sm font-bold text-white">
                    Auto-Accept Edits
                  </label>
                </div>
                <p className="text-[11px] text-white/40 leading-relaxed">
                  {settings.auto_accept_edits
                    ? "✅ File edits will execute without prompting"
                    : "⏳ You'll be asked to approve file changes before execution"}
                </p>
              </div>
              <button
                onClick={() => handleToggle('auto_accept_edits')}
                disabled={loading}
                className={`
                  relative inline-flex h-8 w-14 shrink-0 cursor-pointer rounded-full 
                  border-2 transition-all duration-200
                  ${
                    settings.auto_accept_edits
                      ? 'border-purple-500 bg-purple-500/20'
                      : 'border-white/20 bg-slate-700'
                  }
                  ${loading ? 'opacity-50 cursor-not-allowed' : 'hover:border-purple-400'}
                `}
              >
                <span
                  className={`
                    pointer-events-none inline-block h-7 w-7 transform rounded-full 
                    bg-white shadow-lg transition-transform duration-200
                    ${settings.auto_accept_edits ? 'translate-x-6' : 'translate-x-0'}
                  `}
                />
              </button>
            </div>
          </div>

          {/* ── Plan Mode Toggle ──────────────────────────────────── */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-white/5 hover:border-purple-500/20 transition-all">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">📋</span>
                  <label className="text-sm font-bold text-white">
                    Plan Mode
                  </label>
                </div>
                <p className="text-[11px] text-white/40 leading-relaxed">
                  {settings.plan_mode
                    ? "✅ Eve must plan before executing complex tasks"
                    : "⚡ Eve executes immediately without planning"}
                </p>
              </div>
              <button
                onClick={() => handleToggle('plan_mode')}
                disabled={loading}
                className={`
                  relative inline-flex h-8 w-14 shrink-0 cursor-pointer rounded-full 
                  border-2 transition-all duration-200
                  ${
                    settings.plan_mode
                      ? 'border-blue-500 bg-blue-500/20'
                      : 'border-white/20 bg-slate-700'
                  }
                  ${loading ? 'opacity-50 cursor-not-allowed' : 'hover:border-blue-400'}
                `}
              >
                <span
                  className={`
                    pointer-events-none inline-block h-7 w-7 transform rounded-full 
                    bg-white shadow-lg transition-transform duration-200
                    ${settings.plan_mode ? 'translate-x-6' : 'translate-x-0'}
                  `}
                />
              </button>
            </div>
          </div>

          {/* ── Max Loop Seconds Slider ───────────────────────────── */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-white/5 hover:border-purple-500/20 transition-all">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">⏱️</span>
                <label className="text-sm font-bold text-white">
                  Max Loop Duration
                </label>
              </div>
              <div className="px-3 py-1 rounded-lg bg-purple-500/10 border border-purple-500/25">
                <span className="text-xs font-mono font-bold text-purple-300">
                  {settings.max_loop_seconds}s
                </span>
              </div>
            </div>
            <p className="text-[11px] text-white/40 mb-3">
              Maximum time Eve will spend on a single task before timing out
            </p>
            <input
              type="range"
              min="10"
              max="600"
              step="10"
              value={settings.max_loop_seconds}
              onChange={(e) => handleSliderChange('max_loop_seconds', parseInt(e.target.value))}
              onMouseUp={() => handleSliderRelease('max_loop_seconds')}
              onTouchEnd={() => handleSliderRelease('max_loop_seconds')}
              disabled={loading}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
            />
            <div className="flex justify-between text-[10px] text-white/30 mt-2">
              <span>10s</span>
              <span>300s (5min)</span>
              <span>600s (10min)</span>
            </div>
          </div>

          {/* ── Last Saved Timestamp ──────────────────────────────── */}
          {lastSaved && (
            <div className="px-4 py-2 rounded-lg bg-green-500/5 border border-green-500/20 flex items-center gap-2">
              <span className="text-lg">✅</span>
              <p className="text-[10px] text-green-400/60">
                Settings saved {Math.round((Date.now() - lastSaved) / 1000)}s ago
              </p>
            </div>
          )}

          {/* ── Button Actions ────────────────────────────────────── */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={loadSettings}
              disabled={loading}
              className="flex-1 px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-sm font-semibold transition-colors disabled:opacity-50"
            >
              Reload
            </button>
            <button
              onClick={onClose}
              disabled={loading}
              className="flex-1 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold transition-colors disabled:opacity-50"
            >
              Done
            </button>
          </div>
        </div>

        {/* ── Footer Info ───────────────────────────────────────── */}
        <div className="mt-6 pt-4 border-t border-white/5">
          <p className="text-[10px] text-white/30 text-center">
            Settings are saved automatically when toggled.
            <br />
            Changes apply to new chat sessions immediately.
          </p>
        </div>
      </div>
    </div>
  );
}
