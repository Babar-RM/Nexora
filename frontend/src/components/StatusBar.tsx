import React from 'react';
import { useNexora } from '../store/useNexora';
import { CheckCircle2, XCircle, Clock, FileCode, Cpu } from 'lucide-react';
import { formatMs } from '../lib/utils';

export const StatusBar: React.FC = () => {
  const { result, source, phase } = useNexora();

  const lineCount = source.split('\n').length;
  const timings = result?.timings_ms || {};
  const totalMs = Object.values(timings).reduce((sum, ms) => sum + ms, 0);

  const hasErrors = result?.diagnostics?.some(
    (d) => !d.code.startsWith('W') && !d.phase.toLowerCase().includes('warning')
  );

  return (
    <footer className="h-6 border-t border-border bg-background-secondary px-3 flex items-center justify-between text-[11px] text-foreground-muted select-none font-mono">
      <div className="flex items-center gap-4">
        {/* Compiler Status */}
        {phase === 'compiling' ? (
          <div className="flex items-center gap-1.5 text-accent">
            <div className="w-2.5 h-2.5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            <span>Compiling pipeline...</span>
          </div>
        ) : phase === 'running' ? (
          <div className="flex items-center gap-1.5 text-amber-500">
            <div className="w-2.5 h-2.5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            <span>Executing Python sandbox...</span>
          </div>
        ) : result ? (
          result.ok && !hasErrors ? (
            <div className="flex items-center gap-1 text-success">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Compiled successfully</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-error">
              <XCircle className="w-3.5 h-3.5" />
              <span>Compilation diagnostics found</span>
            </div>
          )
        ) : (
          <span>Ready</span>
        )}

        {/* Timings */}
        {result && (
          <div
            className="flex items-center gap-1 text-foreground-muted hover:text-foreground transition cursor-help"
            title={`Phase breakdown:\n${Object.entries(timings)
              .map(([phase, ms]) => `${phase}: ${ms} ms`)
              .join('\n')}`}
          >
            <Clock className="w-3 h-3" />
            <span>{formatMs(totalMs)}</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Source stats */}
        <div className="flex items-center gap-1">
          <FileCode className="w-3 h-3" />
          <span>{lineCount} lines</span>
        </div>

        {/* Target platform */}
        <div className="flex items-center gap-1">
          <Cpu className="w-3 h-3" />
          <span>Python 3.10+</span>
        </div>
      </div>
    </footer>
  );
};
