/**
 * Nexora Compiler API TypeScript Definitions
 * Aligned with RFC-0009 and api.py.
 */

export interface TokenItem {
  type: string;
  lexeme: string;
  line: number;
  column: number;
  length: number;
  value: any;
}

export interface AstNode {
  kind: string;
  line?: number;
  column?: number;
  resolved_type?: string;
  [key: string]: any;
}

export interface SymbolItem {
  name: string;
  kind: 'variable' | 'task' | 'parameter' | string;
  type: string;
  scope: string;
  line: number;
  column: number;
  constant: boolean;
}

export interface CfgBlock {
  id: string | number;
  label?: string | null;
  instrs?: string[];
  instructions?: string[];
  pred?: (string | number)[];
  predecessors?: (string | number)[];
  succ?: (string | number)[];
  successors?: (string | number)[];
}

export interface CfgFunction {
  function?: string;
  name?: string;
  blocks: CfgBlock[];
  entry: string | number;
  exit?: string | number | null;
}

export interface OptimizationNote {
  level: 'ast' | 'tac';
  line: number;
  message: string;
  before: string;
  after: string;
}

export interface OptimizationReport {
  ast_passes: string[];
  tac_passes: string[];
  notes: OptimizationNote[];
}

export interface DiagnosticItem {
  phase: string;
  code: string;
  line: number;
  column: number;
  length: number;
  message: string;
  hint: string | null;
}

export interface RunResult {
  stdout: string;
  stderr: string;
  exit_code: number | null;
  timed_out: boolean;
  output_truncated: boolean;
  duration_ms: number;
  diagnostics: DiagnosticItem[];
}

export interface CompileResult {
  ok: boolean;
  tokens: TokenItem[] | null;
  ast: AstNode | null;
  symbols: SymbolItem[] | null;
  tac: string[] | null;
  cfg: CfgFunction[] | null;
  optimized_tac: string[] | null;
  optimization: OptimizationReport | null;
  python: string | null;
  python_line_map: number[] | null;
  run: RunResult | null;
  diagnostics: DiagnosticItem[];
  timings_ms: Record<string, number>;
}

export interface CompileRequest {
  source: string;
  run?: boolean;
  optimize?: boolean;
  emit?: string[];
}

export interface ExampleProgram {
  id: string;
  title: string;
  source: string;
}

export interface ErrorCodeMeta {
  code: string;
  phase: string;
  description: string;
}

export interface LanguageInfo {
  keywords: string[];
  types: string[];
  operators: string[];
  punctuation: string[];
  comment_prefix: string;
  error_codes: ErrorCodeMeta[];
}

export interface HealthInfo {
  status: string;
  version: string;
  python: string;
}

export interface ApiError {
  code: string;
  message: string;
}
