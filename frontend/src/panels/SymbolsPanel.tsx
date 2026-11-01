import React, { useState, useMemo } from 'react';
import { useNexora } from '../store/useNexora';
import { Database, AlertTriangle, ArrowUpDown } from 'lucide-react';
import type { SymbolItem } from '../api/schema';

type SortField = 'name' | 'kind' | 'type' | 'scope' | 'line';

export const SymbolsPanel: React.FC = () => {
  const { result, selectRange } = useNexora();
  const [sortField, setSortField] = useState<SortField>('line');
  const [sortAsc, setSortAsc] = useState(true);

  const symbols = result?.symbols || [];

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortedSymbols = useMemo(() => {
    return [...symbols].sort((a, b) => {
      let comparison = 0;
      if (sortField === 'line') {
        comparison = a.line - b.line;
      } else {
        const valA = String(a[sortField] || '');
        const valB = String(b[sortField] || '');
        comparison = valA.localeCompare(valB);
      }
      return sortAsc ? comparison : -comparison;
    });
  }, [symbols, sortField, sortAsc]);

  const handleRowClick = (sym: SymbolItem) => {
    selectRange({
      startLine: sym.line,
      startColumn: sym.column,
      endLine: sym.line,
      endColumn: sym.column + sym.name.length,
    });
  };

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Database className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No symbol table generated yet</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to inspect declared variables, tasks, types, and scopes.
        </p>
      </div>
    );
  }

  if (symbols.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          No symbols found
        </h3>
        <p className="text-xs max-w-sm">
          Semantic analysis did not record any declared symbols or halted early.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header bar */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">Symbol Table</span>
          <span className="text-foreground-muted">•</span>
          <span className="text-foreground-muted">{symbols.length} identifiers declared</span>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead className="bg-background-secondary sticky top-0 z-10 border-b border-border text-[11px] text-foreground-muted uppercase tracking-wider font-sans">
            <tr>
              <th
                onClick={() => handleSort('name')}
                className="py-2 px-3 cursor-pointer hover:text-foreground"
              >
                <div className="flex items-center gap-1">
                  <span>Name</span>
                  <ArrowUpDown className="w-3 h-3" />
                </div>
              </th>
              <th
                onClick={() => handleSort('kind')}
                className="py-2 px-3 cursor-pointer hover:text-foreground"
              >
                <div className="flex items-center gap-1">
                  <span>Kind</span>
                  <ArrowUpDown className="w-3 h-3" />
                </div>
              </th>
              <th
                onClick={() => handleSort('type')}
                className="py-2 px-3 cursor-pointer hover:text-foreground"
              >
                <div className="flex items-center gap-1">
                  <span>Type</span>
                  <ArrowUpDown className="w-3 h-3" />
                </div>
              </th>
              <th
                onClick={() => handleSort('scope')}
                className="py-2 px-3 cursor-pointer hover:text-foreground"
              >
                <div className="flex items-center gap-1">
                  <span>Scope</span>
                  <ArrowUpDown className="w-3 h-3" />
                </div>
              </th>
              <th
                onClick={() => handleSort('line')}
                className="py-2 px-3 text-right cursor-pointer hover:text-foreground"
              >
                <div className="flex items-center justify-end gap-1">
                  <span>Declared At</span>
                  <ArrowUpDown className="w-3 h-3" />
                </div>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {sortedSymbols.map((sym, idx) => (
              <tr
                key={idx}
                onClick={() => handleRowClick(sym)}
                className="hover:bg-accent/10 cursor-pointer transition-colors group"
                title="Click to jump to declaration"
              >
                <td className="py-2 px-3 font-semibold text-foreground group-hover:text-accent">
                  {sym.name}
                </td>
                <td className="py-2 px-3">
                  <span
                    className={`inline-block px-1.5 py-0.5 rounded text-[11px] font-medium border ${
                      sym.kind === 'task'
                        ? 'bg-blue-500/10 text-blue-500 border-blue-500/20'
                        : sym.kind === 'parameter'
                        ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                        : 'bg-background-tertiary text-foreground-muted border-border'
                    }`}
                  >
                    {sym.kind}
                  </span>
                </td>
                <td className="py-2 px-3 text-emerald-500 font-medium">
                  {sym.type}
                </td>
                <td className="py-2 px-3 text-foreground-muted">
                  <span className="bg-background-tertiary px-1.5 py-0.5 rounded text-[11px]">
                    {sym.scope}
                  </span>
                </td>
                <td className="py-2 px-3 text-right text-foreground-muted text-[11px]">
                  line {sym.line}:{sym.column}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
