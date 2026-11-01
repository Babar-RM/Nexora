import { create } from 'zustand';
import type {
  CompileResult,
  ExampleProgram,
  LanguageInfo,
} from '../api/schema';
import {
  compile as apiCompile,
  getExamples as apiGetExamples,
  getLanguage as apiGetLanguage,
} from '../api/client';
import { decodeSource, encodeSource } from '../lib/share';

export type Phase = 'idle' | 'compiling' | 'running';

export type TabId =
  | 'output'
  | 'python'
  | 'tokens'
  | 'ast'
  | 'symbols'
  | 'tac'
  | 'cfg'
  | 'opt'
  | 'problems';

export interface SourceRange {
  startLine: number;
  startColumn: number;
  endLine?: number;
  endColumn?: number;
}

export interface ApiErrorInfo {
  code: string;
  message: string;
  retryAfter?: number;
}

const DEFAULT_SOURCE = `// Welcome to Nexora!
// MiniLang transpile-to-Python demo

task add(x: int, y: int): int {
    give x + y;
}

make a = 10;
make b = 20;
make total = add(a, b);

show("Total sum is: ");
show(total);
`;

function getInitialSource(): string {
  // 1. Try URL hash
  if (typeof window !== 'undefined' && window.location.hash) {
    const decoded = decodeSource(window.location.hash);
    if (decoded) return decoded;
  }

  // 2. Try localStorage
  try {
    const saved = localStorage.getItem('nexora:source');
    if (saved && saved.trim()) return saved;
  } catch (e) {
    // localStorage may be disabled
  }

  // 3. Fallback to default
  return DEFAULT_SOURCE;
}

function getInitialTheme(): 'light' | 'dark' | 'system' {
  try {
    const saved = localStorage.getItem('nexora:theme') as 'light' | 'dark' | 'system' | null;
    if (saved && ['light', 'dark', 'system'].includes(saved)) {
      return saved;
    }
  } catch (e) {}
  return 'dark';
}

interface NexoraStore {
  source: string;
  options: {
    optimize: boolean;
  };
  phase: Phase;
  result: CompileResult | null;
  stale: boolean;
  apiError: ApiErrorInfo | null;
  selection: SourceRange | null;
  activeTab: TabId;
  theme: 'light' | 'dark' | 'system';
  examples: ExampleProgram[];
  language: LanguageInfo | null;
  liveCheckEnabled: boolean;
  showHelp: boolean;

  // Actions
  setSource: (source: string) => void;
  setOptimize: (optimize: boolean) => void;
  setLiveCheck: (enabled: boolean) => void;
  setActiveTab: (tab: TabId) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  selectRange: (range: SourceRange | null) => void;
  setShowHelp: (show: boolean) => void;
  loadExample: (example: ExampleProgram) => void;
  initApp: () => Promise<void>;
  compile: (run?: boolean) => Promise<void>;
  dismissApiError: () => void;
  getShareUrl: () => string;
}

let activeAbortController: AbortController | null = null;

export const useNexora = create<NexoraStore>((set, get) => ({
  source: getInitialSource(),
  options: { optimize: true },
  phase: 'idle',
  result: null,
  stale: false,
  apiError: null,
  selection: null,
  activeTab: 'output',
  theme: getInitialTheme(),
  examples: [],
  language: null,
  liveCheckEnabled: true,
  showHelp: false,

  setSource: (newSource: string) => {
    try {
      localStorage.setItem('nexora:source', newSource);
    } catch (e) {}

    set({ source: newSource, stale: true });
  },

  setOptimize: (optimize: boolean) => {
    set((state) => ({ options: { ...state.options, optimize } }));
    // Re-compile if we have already compiled
    if (get().result) {
      get().compile(false);
    }
  },

  setLiveCheck: (liveCheckEnabled: boolean) => {
    set({ liveCheckEnabled });
  },

  setActiveTab: (activeTab: TabId) => {
    set({ activeTab });
  },

  setTheme: (theme: 'light' | 'dark' | 'system') => {
    try {
      localStorage.setItem('nexora:theme', theme);
    } catch (e) {}

    // Apply class to <html>
    const isDark =
      theme === 'dark' ||
      (theme === 'system' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);

    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }

    set({ theme });
  },

  selectRange: (selection: SourceRange | null) => {
    set({ selection });
  },

  setShowHelp: (showHelp: boolean) => {
    set({ showHelp });
  },

  loadExample: (example: ExampleProgram) => {
    get().setSource(example.source);
    get().compile(false);
  },

  getShareUrl: () => {
    const encoded = encodeSource(get().source);
    const url = new URL(window.location.href);
    url.hash = `src=${encoded}`;
    return url.toString();
  },

  dismissApiError: () => {
    set({ apiError: null });
  },

  initApp: async () => {
    // 1. Set initial theme
    const currentTheme = get().theme;
    get().setTheme(currentTheme);

    // 2. Fetch language specs & examples in parallel
    try {
      const [lang, examples] = await Promise.all([
        apiGetLanguage().catch(() => null),
        apiGetExamples().catch(() => []),
      ]);

      set({
        language: lang,
        examples,
      });
    } catch (e) {
      console.warn('Initial metadata load error:', e);
    }

    // 3. Initial compilation
    get().compile(false);
  },

  compile: async (run: boolean = false) => {
    if (activeAbortController) {
      activeAbortController.abort();
    }
    const controller = new AbortController();
    activeAbortController = controller;

    set({
      phase: run ? 'running' : 'compiling',
      apiError: null,
    });

    try {
      const res = await apiCompile(
        {
          source: get().source,
          run,
          optimize: get().options.optimize,
        },
        controller.signal
      );

      // If aborted, do nothing
      if (controller.signal.aborted) return;

      const hasErrors = res.diagnostics.some(
        (d) => d.phase === 'lexer' || d.phase === 'parser' || d.phase === 'semantic'
      );

      set((state) => ({
        phase: 'idle',
        result: res,
        stale: false,
        apiError: null,
        activeTab: run ? 'output' : hasErrors ? 'problems' : state.activeTab,
      }));
    } catch (err: any) {
      if (err.name === 'AbortError' || controller.signal.aborted) {
        return;
      }

      set({
        phase: 'idle',
        apiError: {
          code: err.code || 'unknown_error',
          message: err.message || 'An unexpected error occurred.',
          retryAfter: err.retryAfter,
        },
      });
    } finally {
      if (activeAbortController === controller) {
        activeAbortController = null;
      }
    }
  },
}));
