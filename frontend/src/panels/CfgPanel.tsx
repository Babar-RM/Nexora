import React, { useState } from 'react';
import { useNexora } from '../store/useNexora';
import { Network, AlertTriangle, ArrowRight, CornerDownRight } from 'lucide-react';
import type { CfgFunction } from '../api/schema';

export const CfgPanel: React.FC = () => {
  const { result } = useNexora();
  const [selectedFuncIndex, setSelectedFuncIndex] = useState(0);

  const cfgs: CfgFunction[] = result?.cfg || [];

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <Network className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No Control Flow Graph</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to visualize the Basic Block Control Flow Graph.
        </p>
      </div>
    );
  }

  if (cfgs.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          No CFG available
        </h3>
        <p className="text-xs max-w-sm">
          Control flow graphs are generated from Three-Address Code blocks.
        </p>
      </div>
    );
  }

  const currentCfg = cfgs[selectedFuncIndex] || cfgs[0];

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Header with Function Selector */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">Control Flow Graph (CFG)</span>
          <span className="text-foreground-muted">•</span>
          <span className="text-foreground-muted">
            {currentCfg.blocks.length} basic blocks
          </span>
        </div>

        {/* Function Dropdown */}
        {cfgs.length > 1 && (
          <div className="flex items-center gap-1.5">
            <span className="text-foreground-muted text-[11px]">Function:</span>
            <select
              value={selectedFuncIndex}
              onChange={(e) => setSelectedFuncIndex(Number(e.target.value))}
              className="bg-background border border-border text-foreground text-xs rounded px-2 py-0.5 focus:outline-none focus:border-accent"
            >
              {cfgs.map((fn, idx) => (
                <option key={idx} value={idx}>
                  {fn.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* CFG Graph Canvas / Blocks View */}
      <div className="flex-1 overflow-auto p-6 bg-background-secondary/30">
        <div className="max-w-3xl mx-auto space-y-6">
          {currentCfg.blocks.map((block) => {
            const isEntry = block.id === currentCfg.entry;
            const isExit = block.id === currentCfg.exit;

            return (
              <div
                key={block.id}
                className="rounded-lg border border-border bg-background shadow-sm overflow-hidden transition hover:border-accent/50"
              >
                {/* Block Header */}
                <div className="px-3.5 py-2 bg-background-secondary border-b border-border flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-bold font-mono text-accent text-sm">
                      {block.id}
                    </span>
                    {isEntry && (
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                        ENTRY
                      </span>
                    )}
                    {isExit && (
                      <span className="px-1.5 py-0.2 rounded-full text-[10px] font-semibold bg-purple-500/15 text-purple-400 border border-purple-500/30">
                        EXIT
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 text-[11px] text-foreground-muted font-mono">
                    {block.predecessors.length > 0 && (
                      <span>Preds: [{block.predecessors.join(', ')}]</span>
                    )}
                    {block.successors.length > 0 && (
                      <span className="text-accent">
                        Succs: [{block.successors.join(', ')}]
                      </span>
                    )}
                  </div>
                </div>

                {/* Instructions */}
                <div className="p-3 font-mono text-xs space-y-1 bg-background">
                  {block.instructions.length > 0 ? (
                    block.instructions.map((instr, i) => (
                      <div
                        key={i}
                        className="text-foreground pl-2 py-0.5 border-l-2 border-transparent hover:border-accent"
                      >
                        {instr}
                      </div>
                    ))
                  ) : (
                    <div className="text-foreground-muted italic text-[11px] pl-2">
                      (empty block)
                    </div>
                  )}
                </div>

                {/* Exit Connectors / Branch edges */}
                {block.successors.length > 0 && (
                  <div className="px-3.5 py-1.5 bg-background-secondary/60 border-t border-border flex items-center gap-3 text-xs">
                    <CornerDownRight className="w-3.5 h-3.5 text-foreground-muted" />
                    <span className="text-[11px] text-foreground-muted">Flows to:</span>
                    <div className="flex items-center gap-2">
                      {block.successors.map((succ, sIdx) => (
                        <div
                          key={sIdx}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-background border border-border text-[11px] font-mono text-foreground font-semibold"
                        >
                          <ArrowRight className="w-3 h-3 text-accent" />
                          <span>{succ}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
