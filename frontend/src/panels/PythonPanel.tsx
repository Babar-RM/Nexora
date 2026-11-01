import React, { useState } from 'react';
import Editor from '@monaco-editor/react';
import { useNexora } from '../store/useNexora';
import { Copy, Check, Download, Code2, AlertTriangle } from 'lucide-react';
import { DARK_THEME, LIGHT_THEME } from '../editor/themes';

export const PythonPanel: React.FC = () => {
  const { result, theme, selectRange } = useNexora();
  const [copied, setCopied] = useState(false);

  const pythonCode = result?.python || '';
  const lineMap = result?.python_line_map || [];

  const handleCopy = async () => {
    if (!pythonCode) return;
    try {
      await navigator.clipboard.writeText(pythonCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.warn('Failed to copy to clipboard', e);
    }
  };

  const handleDownload = () => {
    if (!pythonCode) return;
    const blob = new Blob([pythonCode], { type: 'text/x-python;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nexora_transpiled.py';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Code2 className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No Python code generated yet</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to see the validated, transpiled Python 3.10+ source.
        </p>
      </div>
    );
  }

  if (!result.ok && !pythonCode) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          Compilation halted before code generation
        </h3>
        <p className="text-xs max-w-sm">
          Fix the syntax or semantic errors in the Problems tab to produce Python code.
        </p>
      </div>
    );
  }

  const monacoTheme =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? DARK_THEME
      : LIGHT_THEME;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header Actions */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-background-secondary text-xs">
        <div className="flex items-center gap-2 text-foreground-muted">
          <span className="font-semibold text-foreground">Python 3.10+ Transpiled</span>
          <span>•</span>
          <span>{pythonCode.split('\n').length} lines</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-background-tertiary hover:bg-border text-foreground transition text-xs font-medium"
            title="Copy Python Code"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-success" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy</span>
              </>
            )}
          </button>

          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-background-tertiary hover:bg-border text-foreground transition text-xs font-medium"
            title="Download .py file"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download .py</span>
          </button>
        </div>
      </div>

      {/* Python Code Editor */}
      <div className="flex-1 relative overflow-hidden">
        <Editor
          height="100%"
          language="python"
          theme={monacoTheme}
          value={pythonCode}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            lineHeight: 20,
            fontFamily: "'Fira Code', monospace",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: 'on',
            lineNumbers: 'on',
            padding: { top: 8, bottom: 8 },
            renderLineHighlight: 'all',
          }}
          onMount={(editor) => {
            // When user clicks a line in Python editor, cross-highlight source line from python_line_map
            editor.onDidChangeCursorPosition((e) => {
              const pyLine = e.position.lineNumber;
              if (lineMap && pyLine <= lineMap.length) {
                const srcLine = lineMap[pyLine - 1];
                if (srcLine && srcLine > 0) {
                  selectRange({
                    startLine: srcLine,
                    startColumn: 1,
                    endLine: srcLine,
                    endColumn: 100,
                  });
                }
              }
            });
          }}
        />
      </div>
    </div>
  );
};
