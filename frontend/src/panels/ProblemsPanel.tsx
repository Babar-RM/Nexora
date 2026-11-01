import React, { useState, useMemo } from 'react';
import { useNexora } from '../store/useNexora';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import type { DiagnosticItem } from '../api/schema';

export const ProblemsPanel: React.FC = () => {
  const { result, selectRange, language } = useNexora();
  const [filter, setFilter] = useState<'all' | 'errors' | 'warnings'>('all');

  const diagnostics = result?.diagnostics || [];

  const errorCodesMap = useMemo(() => {
    const map = new Map<string, string>();
    if (language?.error_codes) {
      for (const item of language.error_codes) {
        map.set(item.code, item.description);
      }
    }
    return map;
  }, [language]);

  const filtered = useMemo(() => {
    if (filter === 'errors') {
      return diagnostics.filter(
        (d) => !d.code.startsWith('W') && !d.phase.toLowerCase().includes('warning')
      );
    }
    if (filter === 'warnings') {
      return diagnostics.filter(
        (d) => d.code.startsWith('W') || d.phase.toLowerCase().includes('warning')
      );
    }
    return diagnostics;
  }, [diagnostics, filter]);

  const errorCount = diagnostics.filter(
    (d) => !d.code.startsWith('W') && !d.phase.toLowerCase().includes('warning')
  ).length;

  const warningCount = diagnostics.filter(
    (d) => d.code.startsWith('W') || d.phase.toLowerCase().includes('warning')
  ).length;

  const handleJump = (diag: DiagnosticItem) => {
    selectRange({
      startLine: Math.max(1, diag.line),
      startColumn: Math.max(1, diag.column),
      endLine: Math.max(1, diag.line),
      endColumn: Math.max(1, diag.column + (diag.length || 1)),
    });
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Filter and Count Header */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 font-semibold text-foreground">
            <AlertCircle className="w-4 h-4 text-error" />
            <span>{errorCount} Errors</span>
          </div>
          <div className="flex items-center gap-1.5 font-semibold text-foreground-muted">
            <AlertTriangle className="w-4 h-4 text-warning" />
            <span>{warningCount} Warnings</span>
          </div>
        </div>

        {/* Severity Filter */}
        <div className="flex items-center bg-background rounded border border-border p-0.5">
          <button
            onClick={() => setFilter('all')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
              filter === 'all'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            All ({diagnostics.length})
          </button>
          <button
            onClick={() => setFilter('errors')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
              filter === 'errors'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            Errors ({errorCount})
          </button>
          <button
            onClick={() => setFilter('warnings')}
            className={`px-2 py-0.5 rounded text-[11px] font-medium transition ${
              filter === 'warnings'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            Warnings ({warningCount})
          </button>
        </div>
      </div>

      {/* Diagnostics List */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {filtered.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-foreground-muted text-center">
            <CheckCircle2 className="w-10 h-10 stroke-1 mb-2 text-success opacity-80" />
            <h4 className="text-sm font-semibold text-foreground mb-0.5">
              No problems detected
            </h4>
            <p className="text-xs">Your MiniLang code passed lexical, syntax, and type checks without errors.</p>
          </div>
        ) : (
          filtered.map((diag, idx) => {
            const isWarning =
              diag.code.startsWith('W') || diag.phase.toLowerCase().includes('warning');
            const codeDesc = errorCodesMap.get(diag.code);

            return (
              <div
                key={idx}
                onClick={() => handleJump(diag)}
                className={`p-3 rounded-lg border transition cursor-pointer group ${
                  isWarning
                    ? 'border-warning-border bg-warning-bg/40 hover:bg-warning-bg/70'
                    : 'border-error-border bg-error-bg/30 hover:bg-error-bg/60'
                }`}
                title={`Jump to line ${diag.line}:${diag.column}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5">
                    {isWarning ? (
                      <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-error shrink-0 mt-0.5" />
                    )}

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-xs">
                          [{diag.code}]
                        </span>
                        {codeDesc && (
                          <span className="text-[11px] text-foreground-muted">
                            ({codeDesc})
                          </span>
                        )}
                        <span className="px-1.5 py-0.2 rounded text-[10px] uppercase font-semibold bg-background-tertiary text-foreground-muted">
                          {diag.phase}
                        </span>
                      </div>

                      <div className="text-xs font-medium text-foreground mt-1">
                        {diag.message}
                      </div>

                      {diag.hint && (
                        <div className="text-[11px] text-foreground-muted mt-1 bg-background/50 p-1.5 rounded border border-border/50">
                          <strong className="text-foreground">Hint:</strong> {diag.hint}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 text-[11px] font-mono text-accent shrink-0 group-hover:underline">
                    <span>
                      {diag.line}:{diag.column}
                    </span>
                    <ExternalLink className="w-3 h-3" />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
