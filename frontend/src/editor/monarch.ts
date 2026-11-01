import type { Monaco } from '@monaco-editor/react';
import type { LanguageInfo } from '../api/schema';

export const LANGUAGE_ID = 'minilang';

const DEFAULT_KEYWORDS = [
  'make',
  'show',
  'ask',
  'when',
  'otherwise',
  'during',
  'task',
  'give',
  'yes',
  'no',
  'both',
  'either',
  'not',
  'empty',
  'stop',
  'skip',
];

const DEFAULT_TYPES = ['int', 'float', 'string', 'bool', 'empty', 'void'];

const DEFAULT_OPERATORS = [
  'either',
  'both',
  'not',
  '==',
  '!=',
  '<',
  '<=',
  '>',
  '>=',
  '+',
  '-',
  '*',
  '/',
  '%',
  '=',
];

export function registerMiniLang(monaco: Monaco, langInfo?: LanguageInfo | null) {
  const keywords = langInfo?.keywords?.length ? langInfo.keywords : DEFAULT_KEYWORDS;
  const types = langInfo?.types?.length ? langInfo.types : DEFAULT_TYPES;
  const operators = langInfo?.operators?.length ? langInfo.operators : DEFAULT_OPERATORS;

  // Check if already registered
  const languages = monaco.languages.getLanguages();
  if (!languages.some((lang: { id: string }) => lang.id === LANGUAGE_ID)) {
    monaco.languages.register({ id: LANGUAGE_ID });
  }

  // Language configuration (brackets, comments, indentation)
  monaco.languages.setLanguageConfiguration(LANGUAGE_ID, {
    comments: {
      lineComment: '//',
    },
    brackets: [
      ['{', '}'],
      ['(', ')'],
    ],
    autoClosingPairs: [
      { open: '{', close: '}' },
      { open: '(', close: ')' },
      { open: '"', close: '"', notIn: ['string'] },
    ],
    surroundingPairs: [
      { open: '{', close: '}' },
      { open: '(', close: ')' },
      { open: '"', close: '"' },
    ],
    indentationRules: {
      increaseIndentPattern: /^.*\{[^}"']*$/,
      decreaseIndentPattern: /^\s*\}/,
    },
  });

  // Monarch syntax highlighter definition
  monaco.languages.setMonarchTokensProvider(LANGUAGE_ID, {
    keywords,
    types,
    operators,
    tokenizer: {
      root: [
        // Comments
        [/\/\/.*$/, 'comment'],

        // Function definition: task identifier
        [/\b(task)\s+([a-zA-Z_]\w*)/, ['keyword', 'entity.name.function']],

        // Identifiers, keywords, types
        [
          /[a-zA-Z_]\w*/,
          {
            cases: {
              '@keywords': 'keyword',
              '@types': 'type',
              '@default': 'identifier',
            },
          },
        ],

        // Numbers (floats and ints)
        [/\d*\.\d+([eE][-+]?\d+)?/, 'number.float'],
        [/\d+/, 'number'],

        // Strings with escapes
        [/"([^"\\]|\\.)*$/, 'string.invalid'], // non-terminated string
        [
          /"/,
          {
            token: 'string.quote',
            bracket: '@open',
            next: '@string',
          },
        ],

        // Delimiters and operators
        [/[{}()[\]]/, '@brackets'],
        [/[;,:]/, 'delimiter'],
        [
          /[<>!=+\-*/%]=?/,
          {
            cases: {
              '@operators': 'operator',
              '@default': '',
            },
          },
        ],

        // Whitespace
        { include: '@whitespace' },
      ],

      string: [
        [/[^\\"]+/, 'string'],
        [/\\./, 'string.escape'],
        [/"/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
      ],

      whitespace: [[/[ \t\r\n]+/, 'white']],
    },
  });
}
