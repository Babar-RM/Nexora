import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useNexora } from '../store/useNexora';
import { OutputPanel } from '../panels/OutputPanel';
import { ProblemsPanel } from '../panels/ProblemsPanel';
import { TokensPanel } from '../panels/TokensPanel';
import { SymbolsPanel } from '../panels/SymbolsPanel';
import { TacPanel } from '../panels/TacPanel';
import { CfgPanel } from '../panels/CfgPanel';

describe('Inspector Panels (RFC-0010 §3.8)', () => {
  beforeEach(() => {
    useNexora.setState({
      result: null,
      phase: 'idle',
      selection: null,
    });
  });

  describe('OutputPanel', () => {
    it('renders empty state when no run has occurred', () => {
      render(<OutputPanel />);
      expect(screen.getByText(/No execution output yet/i)).toBeInTheDocument();
      expect(screen.getByText(/Run Program Now/i)).toBeInTheDocument();
    });

    it('renders stdout and exit code when run is available', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [],
          ast: { kind: 'Program' },
          symbols: [],
          tac: [],
          cfg: [],
          optimized_tac: [],
          optimization: { ast_passes: [], tac_passes: [], notes: [] },
          python: 'print("Hello")',
          python_line_map: [1],
          run: {
            stdout: '30\n',
            stderr: '',
            exit_code: 0,
            timed_out: false,
            output_truncated: false,
            duration_ms: 15,
            diagnostics: [],
          },
          diagnostics: [],
          timings_ms: { run: 15 },
        },
      });

      render(<OutputPanel />);
      expect(screen.getByText('30')).toBeInTheDocument();
      expect(screen.getByText(/Exit Code: 0/i)).toBeInTheDocument();
      expect(screen.getByText(/15 ms/i)).toBeInTheDocument();
    });
  });

  describe('ProblemsPanel', () => {
    it('renders clean state when no diagnostics exist', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [],
          ast: { kind: 'Program' },
          symbols: [],
          tac: [],
          cfg: [],
          optimized_tac: [],
          optimization: { ast_passes: [], tac_passes: [], notes: [] },
          python: '',
          python_line_map: [],
          run: null,
          diagnostics: [],
          timings_ms: {},
        },
      });

      render(<ProblemsPanel />);
      expect(screen.getByText(/No problems detected/i)).toBeInTheDocument();
    });

    it('renders diagnostics with jump to line and column', () => {
      useNexora.setState({
        result: {
          ok: false,
          tokens: [],
          ast: null,
          symbols: [],
          tac: [],
          cfg: [],
          optimized_tac: [],
          optimization: null,
          python: null,
          python_line_map: null,
          run: null,
          diagnostics: [
            {
              phase: 'semantic',
              code: 'E3001',
              line: 5,
              column: 8,
              length: 4,
              message: "undeclared variable 'val'",
              hint: 'Declare before use.',
            },
          ],
          timings_ms: {},
        },
      });

      render(<ProblemsPanel />);
      expect(screen.getByText(/1 Errors/i)).toBeInTheDocument();
      expect(screen.getByText(/\[E3001\]/i)).toBeInTheDocument();
      expect(screen.getByText(/undeclared variable 'val'/i)).toBeInTheDocument();

      // Click to jump
      const item = screen.getByText(/\[E3001\]/i).closest('div');
      if (item) fireEvent.click(item);

      const selection = useNexora.getState().selection;
      expect(selection).toEqual({
        startLine: 5,
        startColumn: 8,
        endLine: 5,
        endColumn: 12,
      });
    });
  });

  describe('TokensPanel', () => {
    it('renders token table and filters correctly', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [
            { type: 'MAKE', lexeme: 'make', line: 1, column: 1, length: 4, value: null },
            { type: 'IDENT', lexeme: 'foo', line: 1, column: 6, length: 3, value: 'foo' },
          ],
          ast: null,
          symbols: null,
          tac: null,
          cfg: null,
          optimized_tac: null,
          optimization: null,
          python: null,
          python_line_map: null,
          run: null,
          diagnostics: [],
          timings_ms: {},
        },
      });

      render(<TokensPanel />);
      expect(screen.getByText('MAKE')).toBeInTheDocument();
      expect(screen.getByText('foo')).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText(/Filter tokens/i);
      fireEvent.change(searchInput, { target: { value: 'MAKE' } });

      expect(screen.getByText('MAKE')).toBeInTheDocument();
      expect(screen.queryByText('foo')).not.toBeInTheDocument();
    });
  });

  describe('SymbolsPanel', () => {
    it('renders symbol table with sorting', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [],
          ast: null,
          symbols: [
            { name: 'beta', kind: 'variable', type: 'int', scope: 'global', line: 2, column: 1, constant: false },
            { name: 'alpha', kind: 'variable', type: 'string', scope: 'global', line: 1, column: 1, constant: false },
          ],
          tac: null,
          cfg: null,
          optimized_tac: null,
          optimization: null,
          python: null,
          python_line_map: null,
          run: null,
          diagnostics: [],
          timings_ms: {},
        },
      });

      render(<SymbolsPanel />);
      expect(screen.getByText('alpha')).toBeInTheDocument();
      expect(screen.getByText('beta')).toBeInTheDocument();
    });
  });

  describe('TacPanel', () => {
    it('allows toggling between Raw TAC, Optimized TAC, and Diff View', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [],
          ast: null,
          symbols: [],
          tac: ['B0:', '  t0 = 2 + 3', '  a = t0'],
          cfg: [],
          optimized_tac: ['B0:', '  a = 5'],
          optimization: { ast_passes: [], tac_passes: [], notes: [] },
          python: null,
          python_line_map: null,
          run: null,
          diagnostics: [],
          timings_ms: {},
        },
      });

      render(<TacPanel />);
      expect(screen.getByText(/Raw TAC/i)).toBeInTheDocument();
      expect(screen.getByText(/t0 = 2 \+ 3/i)).toBeInTheDocument();

      // Switch to Optimized
      fireEvent.click(screen.getByText(/Optimized/i));
      expect(screen.getByText(/a = 5/i)).toBeInTheDocument();

      // Switch to Diff View
      fireEvent.click(screen.getByText(/Diff View/i));
      expect(screen.getByText(/Raw TAC \(3 lines\)/i)).toBeInTheDocument();
      expect(screen.getByText(/Optimized TAC \(2 lines\)/i)).toBeInTheDocument();
    });
  });

  describe('CfgPanel', () => {
    it('renders control flow graph blocks with backend IR format without crashing', () => {
      useNexora.setState({
        result: {
          ok: true,
          tokens: [],
          ast: null,
          symbols: [],
          tac: [],
          cfg: [
            {
              function: '__main__',
              entry: 0,
              blocks: [
                {
                  id: 0,
                  label: null,
                  instrs: ['a = 20', 'print a', 'return'],
                  succ: [1],
                  pred: [],
                },
                {
                  id: 1,
                  label: null,
                  instrs: ['return'],
                  succ: [],
                  pred: [0],
                },
              ],
            },
          ],
          optimized_tac: [],
          optimization: null,
          python: null,
          python_line_map: null,
          run: null,
          diagnostics: [],
          timings_ms: {},
        },
      });

      render(<CfgPanel />);
      expect(screen.getByText(/Control Flow Graph/i)).toBeInTheDocument();
      expect(screen.getByText(/__main__/i)).toBeInTheDocument();
      expect(screen.getByText('B0')).toBeInTheDocument();
      expect(screen.getByText('a = 20')).toBeInTheDocument();
    });
  });
});

