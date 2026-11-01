import React from 'react';
import { useNexora, type TabId } from '../store/useNexora';
import {
  Terminal,
  Code2,
  Hash,
  FolderTree,
  Database,
  Layers,
  Network,
  Sparkles,
  AlertCircle,
} from 'lucide-react';

interface TabItem {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  showCount?: boolean;
}

const TABS: TabItem[] = [
  { id: 'output', label: 'Output', icon: Terminal },
  { id: 'python', label: 'Python', icon: Code2 },
  { id: 'tokens', label: 'Tokens', icon: Hash },
  { id: 'ast', label: 'AST', icon: FolderTree },
  { id: 'symbols', label: 'Symbols', icon: Database },
  { id: 'tac', label: 'TAC', icon: Layers },
  { id: 'cfg', label: 'CFG', icon: Network },
  { id: 'opt', label: 'Optimization', icon: Sparkles },
  { id: 'problems', label: 'Problems', icon: AlertCircle, showCount: true },
];

export const Tabs: React.FC = () => {
  const { activeTab, setActiveTab, result } = useNexora();

  const diagnosticCount = result?.diagnostics?.length || 0;
  const hasErrors = result?.diagnostics?.some(
    (d) => !d.code.startsWith('W') && !d.phase.toLowerCase().includes('warning')
  );

  return (
    <div
      role="tablist"
      aria-label="Compiler Inspector Tabs"
      className="flex items-center overflow-x-auto border-b border-border bg-background-secondary/50 px-2 select-none"
    >
      {TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
            aria-selected={isActive}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors whitespace-nowrap ${
              isActive
                ? 'border-accent text-accent font-semibold bg-background'
                : 'border-transparent text-foreground-muted hover:text-foreground hover:bg-background-tertiary/50'
            }`}
          >
            <Icon
              className={`w-3.5 h-3.5 ${
                isActive
                  ? 'text-accent'
                  : tab.id === 'problems' && diagnosticCount > 0
                  ? hasErrors
                    ? 'text-error'
                    : 'text-warning'
                  : 'text-foreground-muted'
              }`}
            />
            <span>{tab.label}</span>

            {tab.showCount && diagnosticCount > 0 && (
              <span
                aria-live="polite"
                className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                  hasErrors
                    ? 'bg-error/15 text-error border border-error-border'
                    : 'bg-warning/15 text-warning border border-warning-border'
                }`}
              >
                {diagnosticCount}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};
