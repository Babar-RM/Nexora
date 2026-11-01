import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: 'var(--bg-primary)',
        'background-secondary': 'var(--bg-secondary)',
        'background-tertiary': 'var(--bg-tertiary)',
        foreground: 'var(--text-primary)',
        'foreground-muted': 'var(--text-muted)',
        border: 'var(--border-color)',
        accent: {
          DEFAULT: 'var(--accent-primary)',
          hover: 'var(--accent-hover)',
          active: 'var(--accent-active)',
          text: 'var(--accent-text)',
        },
        error: {
          DEFAULT: 'var(--error-color)',
          bg: 'var(--error-bg)',
          border: 'var(--error-border)',
        },
        warning: {
          DEFAULT: 'var(--warning-color)',
          bg: 'var(--warning-bg)',
          border: 'var(--warning-border)',
        },
        success: {
          DEFAULT: 'var(--success-color)',
          bg: 'var(--success-bg)',
        },
      },
      fontFamily: {
        mono: [
          'JetBrains Mono',
          'Fira Code',
          'Cascadia Code',
          'Consolas',
          'ui-monospace',
          'monospace',
        ],
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
