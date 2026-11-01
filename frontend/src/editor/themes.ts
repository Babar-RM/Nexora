import type { Monaco } from '@monaco-editor/react';

export const DARK_THEME = 'nexora-dark';
export const LIGHT_THEME = 'nexora-light';

export function defineThemes(monaco: Monaco) {
  // Dark Theme
  monaco.editor.defineTheme(DARK_THEME, {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: 'c084fc', fontStyle: 'bold' },
      { token: 'type', foreground: '38bdf8' },
      { token: 'string', foreground: '34d399' },
      { token: 'string.quote', foreground: '10b981' },
      { token: 'string.escape', foreground: 'fbbf24' },
      { token: 'number', foreground: 'f59e0b' },
      { token: 'number.float', foreground: 'fb923c' },
      { token: 'comment', foreground: '64748b', fontStyle: 'italic' },
      { token: 'operator', foreground: 'f472b6' },
      { token: 'entity.name.function', foreground: '60a5fa', fontStyle: 'bold' },
      { token: 'identifier', foreground: 'e2e8f0' },
    ],
    colors: {
      'editor.background': '#0b0f19',
      'editor.foreground': '#f9fafb',
      'editorCursor.foreground': '#818cf8',
      'editor.lineHighlightBackground': '#11182788',
      'editorLineNumber.foreground': '#475569',
      'editorLineNumber.activeForeground': '#cbd5e1',
      'editor.selectionBackground': '#4338ca55',
      'editorGutter.background': '#0b0f19',
    },
  });

  // Light Theme
  monaco.editor.defineTheme(LIGHT_THEME, {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: '7e22ce', fontStyle: 'bold' },
      { token: 'type', foreground: '0284c7' },
      { token: 'string', foreground: '059669' },
      { token: 'string.quote', foreground: '047857' },
      { token: 'string.escape', foreground: 'd97706' },
      { token: 'number', foreground: 'd97706' },
      { token: 'number.float', foreground: 'ea580c' },
      { token: 'comment', foreground: '94a3b8', fontStyle: 'italic' },
      { token: 'operator', foreground: 'db2777' },
      { token: 'entity.name.function', foreground: '2563eb', fontStyle: 'bold' },
      { token: 'identifier', foreground: '0f172a' },
    ],
    colors: {
      'editor.background': '#ffffff',
      'editor.foreground': '#0f172a',
      'editorCursor.foreground': '#4f46e5',
      'editor.lineHighlightBackground': '#f1f5f9',
      'editorLineNumber.foreground': '#94a3b8',
      'editorLineNumber.activeForeground': '#334155',
      'editor.selectionBackground': '#c7d2fe88',
      'editorGutter.background': '#ffffff',
    },
  });
}
