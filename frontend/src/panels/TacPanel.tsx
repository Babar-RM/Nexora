import React, { useState } from 'react';
import { useNexora } from '../store/useNexora';
import { Layers, AlertTriangle, GitCompare, Sparkles, FileText } from 'lucide-react';

export const TacPanel: React.FC = () => {
  const { result } = useNexora();
  const [viewMode, setViewMode] = useState<'raw' | 'optimized' | 'diff'>('raw');

  const rawTac = result?.tac || [];
  const optTac = result?.optimized_tac || [];

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Layers className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No Three-Address Code yet</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to inspect TAC Intermediate Representation.
        </p>
      </div>
    );
  }

  if (rawTac.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          IR Generation halted
        </h3>
        <p className="text-xs max-w-sm">
          TAC generation requires an error-free typed AST. Check the Problems tab.
        </p>
      </div>
    );
  }

  const activeInstructions = viewMode === 'optimized' ? optTac : rawTac;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header with Mode Toggles */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">Three-Address Code (TAC)</span>
          <span className="text-foreground-muted">•</span>
          <span className="text-foreground-muted">
            {activeInstructions.length} instructions
          </span>
        </div>

        {/* View Mode Selector */}
        <div className="flex items-center bg-background rounded border border-border p-0.5">
          <button
            onClick={() => setViewMode('raw')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition ${
              viewMode === 'raw'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            <FileText className="w-3 h-3" />
            <span>Raw TAC</span>
          </button>
          <button
            onClick={() => setViewMode('optimized')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition ${
              viewMode === 'optimized'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3 h-3" />
            <span>Optimized</span>
          </button>
          <button
            onClick={() => setViewMode('diff')}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition ${
              viewMode === 'diff'
                ? 'bg-accent text-accent-text shadow-sm'
                : 'text-foreground-muted hover:text-foreground'
            }`}
          >
            <GitCompare className="w-3 h-3" />
            <span>Diff View</span>
          </button>
        </div>
      </div>

      {/* Main Instruction Area */}
      <div className="flex-1 overflow-auto p-4 font-mono text-xs">
        {viewMode === 'diff' ? (
          /* Side-by-side Diff View */
          <div className="grid grid-cols-2 gap-4 h-full">
            <div className="border border-border rounded p-3 bg-background-secondary/50 overflow-auto">
              <div className="text-[11px] font-sans font-semibold text-foreground-muted uppercase tracking-wider mb-2 pb-1 border-b border-border">
                Raw TAC ({rawTac.length} lines)
              </div>
              <div className="space-y-0.5">
                {rawTac.map((line, idx) => {
                  const isBlockHeader = line.trim().endsWith(':');
                  const isChanged = !optTac.includes(line);
                  return (
                    <div
                      key={idx}
                      className={`flex items-center px-1.5 py-0.5 rounded ${
                        isBlockHeader
                          ? 'font-bold text-accent pt-2'
                          : isChanged
                          ? 'bg-error/10 text-error line-through decoration-error/50'
                          : 'text-foreground'
                      }`}
                    >
                      <span className="w-6 text-[10px] text-foreground-muted/60 select-none mr-2">
                        {idx + 1}
                      </span>
                      <span>{line}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="border border-border rounded p-3 bg-background-secondary/50 overflow-auto">
              <div className="text-[11px] font-sans font-semibold text-foreground-muted uppercase tracking-wider mb-2 pb-1 border-b border-border">
                Optimized TAC ({optTac.length} lines)
              </div>
              <div className="space-y-0.5">
                {optTac.map((line, idx) => {
                  const isBlockHeader = line.trim().endsWith(':');
                  const isNew = !rawTac.includes(line);
                  return (
                    <div
                      key={idx}
                      className={`flex items-center px-1.5 py-0.5 rounded ${
                        isBlockHeader
                          ? 'font-bold text-accent pt-2'
                          : isNew
                          ? 'bg-success/15 text-success font-medium'
                          : 'text-foreground'
                      }`}
                    >
                      <span className="w-6 text-[10px] text-foreground-muted/60 select-none mr-2">
                        {idx + 1}
                      </span>
                      <span>{line}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* Single Column Listing (Raw or Optimized) */
          <div className="space-y-1">
            {activeInstructions.map((line, idx) => {
              const isBlockHeader = line.trim().endsWith(':');
              return (
                <div
                  key={idx}
                  className={`flex items-center px-2 py-0.5 rounded transition ${
                    isBlockHeader
                      ? 'font-bold text-accent text-sm pt-3 pb-1 border-b border-border/40'
                      : 'hover:bg-accent/10 text-foreground'
                  }`}
                >
                  <span className="w-8 text-[11px] text-foreground-muted/60 select-none mr-3 text-right">
                    {idx + 1}
                  </span>
                  <span className={isBlockHeader ? '' : 'pl-4'}>{line}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
