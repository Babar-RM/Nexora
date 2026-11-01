import React from 'react';
import { useNexora } from '../store/useNexora';
import { Terminal, AlertCircle, Clock, CheckCircle2, XCircle } from 'lucide-react';

export const OutputPanel: React.FC = () => {
  const { result, phase, compile } = useNexora();
  const run = result?.run;

  if (phase === 'running') {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-medium">Running program in sandboxed Python subprocess...</p>
        <span className="text-xs text-foreground-muted/70 mt-1">Wall-clock timeout: 5.0 seconds</span>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Terminal className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No execution output yet</h3>
        <p className="text-xs max-w-sm mb-4">
          Click the "Run" button in the toolbar or press{' '}
          <kbd className="px-1.5 py-0.5 rounded bg-background-tertiary border border-border text-[11px] font-mono">
            Ctrl+Shift+Enter
          </kbd>{' '}
          to execute this MiniLang program in a secure sandbox.
        </p>
        <button
          onClick={() => compile(true)}
          className="px-3.5 py-1.5 bg-accent hover:bg-accent-hover text-accent-text text-xs font-medium rounded shadow-sm transition"
        >
          Run Program Now
        </button>
      </div>
    );
  }

  const isSuccess = run.exit_code === 0 && !run.timed_out;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Run Summary Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-background-secondary text-xs">
        <div className="flex items-center gap-3">
          <div
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-medium ${
              isSuccess
                ? 'bg-success/15 text-success'
                : 'bg-error/15 text-error'
            }`}
          >
            {isSuccess ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : (
              <XCircle className="w-3.5 h-3.5" />
            )}
            <span>
              {run.timed_out
                ? 'Timed Out (5.0s)'
                : run.exit_code !== null
                ? `Exit Code: ${run.exit_code}`
                : 'Execution Failed'}
            </span>
          </div>

          <div className="flex items-center gap-1 text-foreground-muted">
            <Clock className="w-3.5 h-3.5" />
            <span>{run.duration_ms} ms</span>
          </div>
        </div>

        {run.output_truncated && (
          <span className="text-[11px] text-warning bg-warning-bg border border-warning-border px-2 py-0.5 rounded">
            Output truncated (exceeded 64 KB limit)
          </span>
        )}
      </div>

      {/* Runtime Exception Diagnostic Banner */}
      {run.diagnostics && run.diagnostics.length > 0 && (
        <div className="m-3 p-3 rounded border border-error-border bg-error-bg text-error text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold flex items-center gap-2">
              <span>[{run.diagnostics[0].code}] Runtime Error</span>
              <span className="font-mono text-[11px] opacity-80">
                Line {run.diagnostics[0].line}:{run.diagnostics[0].column}
              </span>
            </div>
            <div className="mt-1 font-mono text-[12px]">{run.diagnostics[0].message}</div>
            {run.diagnostics[0].hint && (
              <div className="mt-1 text-[11px] opacity-90">
                Hint: {run.diagnostics[0].hint}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stdout Console */}
      <div className="flex-1 p-4 overflow-auto font-mono text-xs leading-relaxed selection:bg-accent/20">
        {run.stdout ? (
          <pre className="whitespace-pre-wrap">{run.stdout}</pre>
        ) : (
          <span className="text-foreground-muted italic">
            Program finished without printing any output.
          </span>
        )}
      </div>
    </div>
  );
};
