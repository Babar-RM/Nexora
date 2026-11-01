import React, { useState, useMemo } from 'react';
import { useNexora } from '../store/useNexora';
import { Search, Hash, AlertTriangle } from 'lucide-react';
import type { TokenItem } from '../api/schema';

export const TokensPanel: React.FC = () => {
  const { result, selectRange } = useNexora();
  const [filter, setFilter] = useState('');

  const tokens = result?.tokens || [];

  const filteredTokens = useMemo(() => {
    if (!filter.trim()) return tokens;
    const lower = filter.toLowerCase();
    return tokens.filter(
      (t) =>
        t.type.toLowerCase().includes(lower) ||
        t.lexeme.toLowerCase().includes(lower)
    );
  }, [tokens, filter]);

  const handleRowClick = (token: TokenItem) => {
    selectRange({
      startLine: token.line,
      startColumn: token.column,
      endLine: token.line,
      endColumn: token.column + token.length,
    });
  };

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Hash className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No tokens generated yet</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to inspect the Lexer token stream.
        </p>
      </div>
    );
  }

  if (tokens.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          Lexical analysis produced no tokens
        </h3>
        <p className="text-xs max-w-sm">
          Check the Problems tab for lexical errors.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Search Filter Header */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between gap-3 text-xs">
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-foreground-muted" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter tokens (e.g. IDENT, make, 20)..."
            className="w-full pl-8 pr-3 py-1 bg-background border border-border rounded text-xs text-foreground placeholder:text-foreground-muted focus:outline-none focus:border-accent"
          />
        </div>

        <div className="text-foreground-muted">
          Showing <span className="font-semibold text-foreground">{filteredTokens.length}</span> of{' '}
          {tokens.length} tokens
        </div>
      </div>

      {/* Table Container */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead className="bg-background-secondary sticky top-0 z-10 border-b border-border text-[11px] text-foreground-muted uppercase tracking-wider font-sans">
            <tr>
              <th className="py-2 px-3 w-12 text-center">#</th>
              <th className="py-2 px-3 w-36">Type</th>
              <th className="py-2 px-3">Lexeme</th>
              <th className="py-2 px-3 w-24 text-right">Line:Col</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {filteredTokens.map((tok, idx) => (
              <tr
                key={idx}
                onClick={() => handleRowClick(tok)}
                className="hover:bg-accent/10 cursor-pointer transition-colors group"
                title="Click to highlight in editor"
              >
                <td className="py-1.5 px-3 text-foreground-muted text-center text-[11px]">
                  {idx + 1}
                </td>
                <td className="py-1.5 px-3">
                  <span className="inline-block px-1.5 py-0.5 rounded text-[11px] font-medium bg-background-tertiary border border-border group-hover:border-accent/40 text-accent">
                    {tok.type}
                  </span>
                </td>
                <td className="py-1.5 px-3 font-semibold text-foreground break-all">
                  {tok.type === 'STRING' ? `"${tok.lexeme}"` : tok.lexeme}
                </td>
                <td className="py-1.5 px-3 text-right text-foreground-muted text-[11px]">
                  {tok.line}:{tok.column}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
