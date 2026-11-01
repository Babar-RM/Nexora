import type { Monaco } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import type { DiagnosticItem } from '../api/schema';

/**
 * Converts Nexora Diagnostic items into Monaco editor markers.
 * Follows RFC-0010 §3.7.
 */
export function updateMarkers(
  monaco: Monaco,
  editorInstance: editor.IStandaloneCodeEditor,
  diagnostics: DiagnosticItem[]
) {
  const model = editorInstance.getModel();
  if (!model) return;

  const markers: editor.IMarkerData[] = diagnostics.map((diag) => {
    const isWarning =
      diag.code.startsWith('W') || diag.phase.toLowerCase().includes('warning');
    const severity = isWarning
      ? monaco.MarkerSeverity.Warning
      : monaco.MarkerSeverity.Error;

    let message = `[${diag.code}] ${diag.message}`;
    if (diag.hint) {
      message += `\nHint: ${diag.hint}`;
    }

    const startLineNumber = Math.max(1, diag.line);
    const startColumn = Math.max(1, diag.column);
    const length = Math.max(1, diag.length || 1);
    const endColumn = startColumn + length;

    return {
      severity,
      startLineNumber,
      startColumn,
      endLineNumber: startLineNumber,
      endColumn,
      message,
      source: 'Nexora',
    };
  });

  monaco.editor.setModelMarkers(model, 'nexora', markers);
}
