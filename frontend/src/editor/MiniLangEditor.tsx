import React, { useEffect, useRef } from 'react';
import Editor, { type Monaco, type OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { useNexora } from '../store/useNexora';
import { registerMiniLang, LANGUAGE_ID } from './monarch';
import { updateMarkers } from './markers';
import { defineThemes, DARK_THEME, LIGHT_THEME } from './themes';
import { debounce } from '../lib/utils';

export const MiniLangEditor: React.FC = () => {
  const {
    source,
    setSource,
    theme,
    result,
    selection,
    language,
    liveCheckEnabled,
    compile,
  } = useNexora();

  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorationsRef = useRef<string[]>([]);

  // Debounced live-check compilation (RFC-0010 §3.5: 600ms debounce)
  const debouncedLiveCheck = useRef(
    debounce(() => {
      if (useNexora.getState().liveCheckEnabled) {
        useNexora.getState().compile(false);
      }
    }, 600)
  ).current;

  const handleEditorMount: OnMount = (editorInstance, monaco) => {
    editorRef.current = editorInstance;
    monacoRef.current = monaco;

    defineThemes(monaco);
    registerMiniLang(monaco, language);

    // Keyboard Shortcuts (RFC-0010 §3.5)
    // Ctrl/Cmd + Enter -> Compile
    editorInstance.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
      () => {
        compile(false);
      }
    );

    // Ctrl/Cmd + Shift + Enter -> Run
    editorInstance.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter,
      () => {
        compile(true);
      }
    );

    // Initial markers if result already exists
    if (result?.diagnostics) {
      updateMarkers(monaco, editorInstance, result.diagnostics);
    }
  };

  // Update Monarch tokenizer if language metadata changes
  useEffect(() => {
    if (monacoRef.current && language) {
      registerMiniLang(monacoRef.current, language);
    }
  }, [language]);

  // Update Monaco markers whenever compilation result or diagnostics change
  useEffect(() => {
    if (editorRef.current && monacoRef.current) {
      const diagnostics = result?.diagnostics || [];
      updateMarkers(monacoRef.current, editorRef.current, diagnostics);
    }
  }, [result]);

  // Cross-highlighting: scroll and apply decoration when selection in store changes
  useEffect(() => {
    if (!editorRef.current || !monacoRef.current) return;

    if (!selection) {
      decorationsRef.current = editorRef.current.deltaDecorations(
        decorationsRef.current,
        []
      );
      return;
    }

    const { startLine, startColumn, endLine, endColumn } = selection;
    const line = Math.max(1, startLine);
    const col = Math.max(1, startColumn);
    const targetEndLine = Math.max(line, endLine || line);
    const targetEndCol = Math.max(col + 1, endColumn || col + 2);

    editorRef.current.revealLineInCenter(line);
    editorRef.current.setPosition({ lineNumber: line, column: col });

    const newDecorations: editor.IModelDeltaDecoration[] = [
      {
        range: new monacoRef.current.Range(
          line,
          col,
          targetEndLine,
          targetEndCol
        ),
        options: {
          isWholeLine: false,
          className: 'nexora-cross-highlight',
          overviewRuler: {
            color: '#6366f1',
            position: monacoRef.current.editor.OverviewRulerLane.Full,
          },
        },
      },
    ];

    decorationsRef.current = editorRef.current.deltaDecorations(
      decorationsRef.current,
      newDecorations
    );
  }, [selection]);

  const monacoTheme =
    theme === 'dark' ||
    (theme === 'system' &&
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? DARK_THEME
      : LIGHT_THEME;

  return (
    <div className="h-full w-full flex flex-col relative overflow-hidden bg-background">
      <Editor
        height="100%"
        language={LANGUAGE_ID}
        theme={monacoTheme}
        value={source}
        onChange={(val) => {
          setSource(val || '');
          if (liveCheckEnabled) {
            debouncedLiveCheck();
          }
        }}
        onMount={handleEditorMount}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          lineHeight: 22,
          fontFamily: "'Fira Code', monospace",
          fontLigatures: true,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: 'on',
          renderLineHighlight: 'line',
          fixedOverflowWidgets: true,
          quickSuggestions: true,
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
};
