import React, { useState } from 'react';
import { useNexora } from '../store/useNexora';
import {
  Play,
  Hammer,
  Share2,
  Sun,
  Moon,
  Laptop,
  HelpCircle,
  Check,
  ChevronDown,
  Sparkles,
  Zap,
} from 'lucide-react';

export const Toolbar: React.FC = () => {
  const {
    phase,
    options,
    theme,
    examples,
    liveCheckEnabled,
    stale,
    setOptimize,
    setLiveCheck,
    setTheme,
    setShowHelp,
    loadExample,
    compile,
    getShareUrl,
  } = useNexora();

  const [copiedShare, setCopiedShare] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [examplesOpen, setExamplesOpen] = useState(false);

  const handleShare = async () => {
    try {
      setShareError(null);
      const url = getShareUrl();
      await navigator.clipboard.writeText(url);
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2500);
    } catch (err: any) {
      setShareError(err.message || 'Failed to copy link');
      setTimeout(() => setShareError(null), 3500);
    }
  };

  const isWorking = phase !== 'idle';

  return (
    <header className="h-12 border-b border-border bg-background-secondary/80 backdrop-blur px-3 flex items-center justify-between gap-2 select-none z-20">
      {/* Brand & Examples */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 mr-1">
          <div className="w-6 h-6 rounded bg-gradient-to-tr from-accent to-purple-500 flex items-center justify-center text-accent-text font-bold text-xs shadow-sm">
            N
          </div>
          <span className="font-bold tracking-tight text-sm text-foreground">
            Nexora
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-background-tertiary text-foreground-muted border border-border">
            v0.1.0
          </span>
        </div>

        {/* Examples Dropdown */}
        <div className="relative">
          <button
            onClick={() => setExamplesOpen(!examplesOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-background border border-border hover:bg-background-tertiary text-xs font-medium text-foreground transition"
          >
            <span>Examples</span>
            <ChevronDown className="w-3.5 h-3.5 text-foreground-muted" />
          </button>

          {examplesOpen && (
            <div className="absolute left-0 top-full mt-1 w-48 rounded-md bg-background border border-border shadow-lg py-1 z-30">
              {examples.length === 0 ? (
                <div className="px-3 py-1.5 text-xs text-foreground-muted">
                  No examples loaded
                </div>
              ) : (
                examples.map((ex) => (
                  <button
                    key={ex.id}
                    onClick={() => {
                      loadExample(ex);
                      setExamplesOpen(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent/15 hover:text-accent font-medium transition"
                  >
                    {ex.title}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Stale Source Badge per RFC-0010 §3.4 */}
        {stale && (
          <span className="hidden sm:inline-flex items-center text-[11px] px-2 py-0.5 rounded-full bg-warning-bg text-warning border border-warning-border font-medium">
            Modified (uncompiled)
          </span>
        )}
      </div>

      {/* Compiler Action Controls */}
      <div className="flex items-center gap-2">
        {/* Optimize Toggle */}
        <label
          className="hidden md:flex items-center gap-1.5 text-xs text-foreground-muted hover:text-foreground cursor-pointer px-2 py-1 rounded hover:bg-background-tertiary transition"
          title="Enable constant folding and AST/TAC optimization passes"
        >
          <input
            type="checkbox"
            checked={options.optimize}
            onChange={(e) => setOptimize(e.target.checked)}
            className="rounded border-border text-accent focus:ring-accent w-3.5 h-3.5"
          />
          <Sparkles className="w-3.5 h-3.5 text-accent" />
          <span>Optimize</span>
        </label>

        {/* Live-Check Toggle */}
        <label
          className="hidden lg:flex items-center gap-1.5 text-xs text-foreground-muted hover:text-foreground cursor-pointer px-2 py-1 rounded hover:bg-background-tertiary transition"
          title="Perform background syntax check 600ms after editing"
        >
          <input
            type="checkbox"
            checked={liveCheckEnabled}
            onChange={(e) => setLiveCheck(e.target.checked)}
            className="rounded border-border text-accent focus:ring-accent w-3.5 h-3.5"
          />
          <Zap className="w-3.5 h-3.5 text-amber-500" />
          <span>Live Check</span>
        </label>

        <div className="h-4 w-[1px] bg-border mx-1 hidden md:block" />

        {/* Compile Button */}
        <button
          onClick={() => compile(false)}
          disabled={isWorking}
          className="flex items-center gap-1.5 px-3 py-1 rounded bg-background border border-border hover:bg-background-tertiary text-foreground text-xs font-medium transition disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          title="Compile MiniLang source (Ctrl/Cmd+Enter)"
        >
          {phase === 'compiling' ? (
            <div className="w-3.5 h-3.5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          ) : (
            <Hammer className="w-3.5 h-3.5 text-accent" />
          )}
          <span>Compile</span>
          <kbd className="hidden sm:inline-block ml-1 px-1 py-0.2 rounded bg-background-secondary text-[10px] text-foreground-muted border border-border">
            ⌘↵
          </kbd>
        </button>

        {/* Run Button */}
        <button
          onClick={() => compile(true)}
          disabled={isWorking}
          className="flex items-center gap-1.5 px-3 py-1 rounded bg-accent hover:bg-accent-hover text-accent-text text-xs font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed shadow"
          title="Compile and execute in sandboxed Python runner (Ctrl/Cmd+Shift+Enter)"
        >
          {phase === 'running' ? (
            <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span>{phase === 'running' ? 'Running...' : 'Run'}</span>
          <kbd className="hidden sm:inline-block ml-1 px-1 py-0.2 rounded bg-white/20 text-[10px] text-white">
            ⇧⌘↵
          </kbd>
        </button>
      </div>

      {/* Utilities: Share, Theme, Help */}
      <div className="flex items-center gap-1.5">
        {/* Share Button */}
        <div className="relative">
          <button
            onClick={handleShare}
            className="flex items-center gap-1 px-2.5 py-1 rounded hover:bg-background-tertiary text-foreground-muted hover:text-foreground text-xs font-medium transition"
            title="Copy playground share link with code embedded in URL hash"
          >
            {copiedShare ? (
              <>
                <Check className="w-3.5 h-3.5 text-success" />
                <span className="text-success hidden sm:inline">Copied!</span>
              </>
            ) : (
              <>
                <Share2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Share</span>
              </>
            )}
          </button>

          {shareError && (
            <div className="absolute right-0 top-full mt-1 w-52 p-2 rounded bg-error-bg text-error text-[11px] border border-error-border z-30 shadow-md">
              {shareError}
            </div>
          )}
        </div>

        {/* Theme Toggle */}
        <div className="flex items-center bg-background rounded border border-border p-0.5">
          <button
            onClick={() => setTheme('light')}
            className={`p-1 rounded transition ${
              theme === 'light'
                ? 'bg-accent/15 text-accent font-semibold'
                : 'text-foreground-muted hover:text-foreground'
            }`}
            title="Light Theme"
          >
            <Sun className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setTheme('dark')}
            className={`p-1 rounded transition ${
              theme === 'dark'
                ? 'bg-accent/15 text-accent font-semibold'
                : 'text-foreground-muted hover:text-foreground'
            }`}
            title="Dark Theme"
          >
            <Moon className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setTheme('system')}
            className={`p-1 rounded transition ${
              theme === 'system'
                ? 'bg-accent/15 text-accent font-semibold'
                : 'text-foreground-muted hover:text-foreground'
            }`}
            title="System Theme"
          >
            <Laptop className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Help Modal trigger */}
        <button
          onClick={() => setShowHelp(true)}
          className="p-1.5 rounded hover:bg-background-tertiary text-foreground-muted hover:text-foreground transition"
          title="Help & Shortcuts (?)"
        >
          <HelpCircle className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
