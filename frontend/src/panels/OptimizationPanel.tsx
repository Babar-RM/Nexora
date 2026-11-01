import React, { useState, useMemo } from 'react';
import { useNexora } from '../store/useNexora';
import { Sparkles, Info, CheckCircle2, ArrowRight } from 'lucide-react';
import type { OptimizationNote } from '../api/schema';

export const OptimizationPanel: React.FC = () => {
  const { result, selectRange } = useNexora();
  const [levelFilter, setLevelFilter] = useState<'all' | 'ast' | 'tac'>('all');

  const optReport = result?.optimization;
  const notes = optReport?.notes || [];

  const filteredNotes = useMemo(() => {
    if (levelFilter === 'all') return notes;
    return notes.filter((n) => n.level === levelFilter);
  }, [notes, levelFilter]);

  const handleNoteClick = (note: OptimizationNote) => {
    if (note.line && note.line > 0) {
      selectRange({
        startLine: note.line,
        startColumn: 1,
        endLine: note.line,
        endColumn: 80,
      });
    }
  };

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Sparkles className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No optimization report</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program with the "Optimize" option enabled to see constant folding and dead code elimination passes.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Educational Callout Banner per RFC-0010 §3.8 & RFC-0007 §5 */}
      <div className="p-3 bg-accent/10 border-b border-border flex items-start gap-2.5 text-xs text-foreground">
        <Info className="w-4 h-4 text-accent shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <span className="font-semibold text-accent">Compiler Architecture Note:</span>{' '}
          TAC optimization is performed for compiler analysis and study; the final generated Python
          code is emitted directly from the optimized AST to maintain idiomatic control structures.
        </div>
      </div>

      {/* Filter and Summary Bar */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">Passes Applied</span>
          <span className="text-foreground-muted">•</span>
          <span className="text-foreground-muted">{notes.length} transformation notes</span>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center bg-background rounded border border-border p-0.5">
          {(['all', 'ast', 'tac'] as const).map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className={`px-2 py-0.5 rounded text-[11px] font-medium transition uppercase ${
                levelFilter === lvl
                  ? 'bg-accent text-accent-text shadow-sm'
                  : 'text-foreground-muted hover:text-foreground'
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* Passes list overview */}
      {optReport && (
        <div className="px-4 py-2 border-b border-border bg-background-tertiary/40 flex items-center gap-4 text-[11px] text-foreground-muted overflow-x-auto">
          <span>
            AST passes: <strong className="text-foreground">{optReport.ast_passes?.join(', ') || 'None'}</strong>
          </span>
          <span>•</span>
          <span>
            TAC passes: <strong className="text-foreground">{optReport.tac_passes?.join(', ') || 'None'}</strong>
          </span>
        </div>
      )}

      {/* Notes List */}
      <div className="flex-1 overflow-auto p-4 space-y-3">
        {filteredNotes.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-foreground-muted text-center">
            <CheckCircle2 className="w-8 h-8 stroke-1 mb-2 text-success opacity-80" />
            <p className="text-xs">No active transformations needed for this code block.</p>
          </div>
        ) : (
          filteredNotes.map((note, idx) => (
            <div
              key={idx}
              onClick={() => handleNoteClick(note)}
              className="p-3 rounded-lg border border-border bg-background-secondary/50 hover:bg-background-secondary hover:border-accent/50 transition cursor-pointer group"
              title={note.line ? `Click to jump to line ${note.line}` : undefined}
            >
              <div className="flex items-center justify-between text-xs mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                      note.level === 'ast'
                        ? 'bg-purple-500/15 text-purple-400 border border-purple-500/30'
                        : 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                    }`}
                  >
                    {note.level} Level
                  </span>
                  {note.line > 0 && (
                    <span className="text-[11px] text-foreground-muted font-mono">
                      Line {note.line}
                    </span>
                  )}
                </div>
                <span className="text-[11px] text-accent font-medium group-hover:underline">
                  Jump to source →
                </span>
              </div>

              <div className="text-xs font-medium text-foreground mb-2">
                {note.message}
              </div>

              {(note.before || note.after) && (
                <div className="flex items-center gap-2 font-mono text-[11px] bg-background p-2 rounded border border-border">
                  <span className="text-error line-through opacity-80">{note.before}</span>
                  <ArrowRight className="w-3.5 h-3.5 text-accent shrink-0" />
                  <span className="text-success font-semibold">{note.after}</span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
