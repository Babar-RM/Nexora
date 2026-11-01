import React, { useState } from 'react';
import { useNexora } from '../store/useNexora';
import {
  ChevronRight,
  ChevronDown,
  FolderTree,
  AlertTriangle,
  ChevronsUpDown,
  ChevronsDownUp,
} from 'lucide-react';
import type { AstNode } from '../api/schema';

interface AstTreeNodeProps {
  node: any;
  label?: string;
  depth?: number;
  onSelectNode: (node: AstNode) => void;
  defaultExpandedDepth?: number;
}

const AstTreeNode: React.FC<AstTreeNodeProps> = ({
  node,
  label,
  depth = 0,
  onSelectNode,
  defaultExpandedDepth = 2,
}) => {
  const [expanded, setExpanded] = useState(depth <= defaultExpandedDepth);

  if (node === null || node === undefined) {
    return (
      <div className="font-mono text-xs text-foreground-muted ml-4 py-0.5">
        {label && <span className="text-foreground-muted mr-1.5">{label}:</span>}
        <span className="italic text-foreground-muted/60">null</span>
      </div>
    );
  }

  // Primitive value
  if (typeof node !== 'object') {
    return (
      <div className="font-mono text-xs ml-4 py-0.5 flex items-center gap-1.5">
        {label && <span className="text-foreground-muted">{label}:</span>}
        <span
          className={
            typeof node === 'string'
              ? 'text-emerald-500 font-medium'
              : typeof node === 'number'
              ? 'text-amber-500 font-medium'
              : typeof node === 'boolean'
              ? 'text-purple-400 font-medium'
              : 'text-foreground'
          }
        >
          {typeof node === 'string' ? `"${node}"` : String(node)}
        </span>
      </div>
    );
  }

  // Array of items
  if (Array.isArray(node)) {
    if (node.length === 0) {
      return (
        <div className="font-mono text-xs text-foreground-muted ml-4 py-0.5">
          {label && <span className="text-foreground-muted mr-1.5">{label}:</span>}
          <span>[]</span>
        </div>
      );
    }

    return (
      <div className="ml-2 py-0.5 font-mono text-xs">
        <div
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 cursor-pointer hover:text-accent select-none text-foreground-muted"
        >
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
          {label && <span className="font-semibold text-foreground">{label}:</span>}
          <span className="text-[11px] text-foreground-muted">[{node.length} items]</span>
        </div>

        {expanded && (
          <div className="border-l border-border/80 pl-2 ml-1.5 mt-0.5 flex flex-col">
            {node.map((item, idx) => (
              <AstTreeNode
                key={idx}
                node={item}
                label={`[${idx}]`}
                depth={depth + 1}
                onSelectNode={onSelectNode}
                defaultExpandedDepth={defaultExpandedDepth}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // Node Object
  const isAstNode = typeof node.kind === 'string';
  const nodeKind = node.kind || label || 'Node';
  const resolvedType = node.resolved_type;
  const line = node.line;
  const col = node.column;

  // Filter out internal/position metadata keys for display
  const childKeys = Object.keys(node).filter(
    (k) =>
      k !== 'kind' &&
      k !== 'line' &&
      k !== 'column' &&
      k !== 'resolved_type' &&
      k !== 'end_line' &&
      k !== 'end_column'
  );

  return (
    <div className="ml-2 py-0.5 font-mono text-xs">
      <div className="flex items-center gap-1.5 group select-none py-0.5">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-foreground-muted hover:text-foreground p-0.5"
        >
          {childKeys.length > 0 ? (
            expanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )
          ) : (
            <span className="w-3.5 inline-block" />
          )}
        </button>

        {label && <span className="text-foreground-muted">{label}:</span>}

        <div
          onClick={() => isAstNode && onSelectNode(node)}
          className={`flex items-center gap-1.5 rounded px-1.5 py-0.5 transition cursor-pointer ${
            isAstNode
              ? 'hover:bg-accent/15 group-hover:text-accent font-semibold text-foreground'
              : 'text-foreground'
          }`}
          title={isAstNode && line ? `Click to jump to line ${line}:${col}` : undefined}
        >
          <span className="text-accent">{nodeKind}</span>

          {resolvedType && (
            <span className="px-1.5 py-0.2 rounded-full text-[10px] font-medium bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
              :{resolvedType}
            </span>
          )}

          {line !== undefined && col !== undefined && (
            <span className="text-[10px] text-foreground-muted opacity-70">
              ({line}:{col})
            </span>
          )}
        </div>
      </div>

      {expanded && childKeys.length > 0 && (
        <div className="border-l border-border/80 pl-2 ml-1.5 mt-0.5 flex flex-col">
          {childKeys.map((key) => (
            <AstTreeNode
              key={key}
              node={node[key]}
              label={key}
              depth={depth + 1}
              onSelectNode={onSelectNode}
              defaultExpandedDepth={defaultExpandedDepth}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export const AstPanel: React.FC = () => {
  const { result, selectRange } = useNexora();
  const [expandAllKey, setExpandAllKey] = useState(0);
  const [expandDepth, setExpandDepth] = useState(2);

  const ast = result?.ast;

  const handleSelectNode = (node: AstNode) => {
    if (node.line !== undefined && node.column !== undefined) {
      selectRange({
        startLine: node.line,
        startColumn: node.column,
        endLine: node.end_line || node.line,
        endColumn: node.end_column || node.column + 3,
      });
    }
  };

  if (!result) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <FolderTree className="w-12 h-12 stroke-1 mb-3 opacity-40" />
        <h3 className="text-sm font-semibold mb-1">No AST generated yet</h3>
        <p className="text-xs max-w-sm">
          Compile your MiniLang program to inspect the Abstract Syntax Tree.
        </p>
      </div>
    );
  }

  if (!ast) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-foreground-muted p-8 text-center">
        <AlertTriangle className="w-10 h-10 stroke-1 mb-3 text-warning opacity-70" />
        <h3 className="text-sm font-semibold mb-1 text-foreground">
          Parsing failed — no AST available
        </h3>
        <p className="text-xs max-w-sm">
          The parser encountered syntax errors. View the Problems tab to see diagnostics and hints.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* AST Controls Header */}
      <div className="p-2 border-b border-border bg-background-secondary flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">Abstract Syntax Tree</span>
          <span className="text-foreground-muted">•</span>
          <span className="text-foreground-muted">{ast.kind || 'Program'}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => {
              setExpandDepth(6);
              setExpandAllKey((k) => k + 1);
            }}
            className="flex items-center gap-1 px-2 py-1 rounded bg-background border border-border hover:bg-background-tertiary text-foreground text-[11px] font-medium transition"
            title="Expand All Nodes"
          >
            <ChevronsUpDown className="w-3 h-3" />
            <span>Expand</span>
          </button>
          <button
            onClick={() => {
              setExpandDepth(0);
              setExpandAllKey((k) => k + 1);
            }}
            className="flex items-center gap-1 px-2 py-1 rounded bg-background border border-border hover:bg-background-tertiary text-foreground text-[11px] font-medium transition"
            title="Collapse All Nodes"
          >
            <ChevronsDownUp className="w-3 h-3" />
            <span>Collapse</span>
          </button>
        </div>
      </div>

      {/* Interactive Tree View */}
      <div className="flex-1 p-3 overflow-auto">
        <AstTreeNode
          key={expandAllKey}
          node={ast}
          depth={0}
          defaultExpandedDepth={expandDepth}
          onSelectNode={handleSelectNode}
        />
      </div>
    </div>
  );
};
