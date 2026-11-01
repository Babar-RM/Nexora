import React, { useEffect, useState } from 'react';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { useNexora } from './store/useNexora';
import { Toolbar } from './components/Toolbar';
import { Tabs } from './components/Tabs';
import { StatusBar } from './components/StatusBar';
import { ErrorBanner } from './components/ErrorBanner';
import { HelpModal } from './components/HelpModal';
import { MiniLangEditor } from './editor/MiniLangEditor';

import { OutputPanel } from './panels/OutputPanel';
import { PythonPanel } from './panels/PythonPanel';
import { TokensPanel } from './panels/TokensPanel';
import { AstPanel } from './panels/AstPanel';
import { SymbolsPanel } from './panels/SymbolsPanel';
import { TacPanel } from './panels/TacPanel';
import { CfgPanel } from './panels/CfgPanel';
import { OptimizationPanel } from './panels/OptimizationPanel';
import { ProblemsPanel } from './panels/ProblemsPanel';

export const App: React.FC = () => {
  const { activeTab, initApp } = useNexora();
  const [mobileView, setMobileView] = useState<'editor' | 'inspector' | 'problems'>('editor');
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    initApp();

    const handleResize = () => {
      setIsMobile(window.innerWidth < 1024);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [initApp]);

  const renderActivePanel = () => {
    switch (activeTab) {
      case 'output':
        return <OutputPanel />;
      case 'python':
        return <PythonPanel />;
      case 'tokens':
        return <TokensPanel />;
      case 'ast':
        return <AstPanel />;
      case 'symbols':
        return <SymbolsPanel />;
      case 'tac':
        return <TacPanel />;
      case 'cfg':
        return <CfgPanel />;
      case 'opt':
        return <OptimizationPanel />;
      case 'problems':
        return <ProblemsPanel />;
      default:
        return <OutputPanel />;
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-background text-foreground overflow-hidden">
      <Toolbar />
      <ErrorBanner />

      {/* Main Workspace Layout */}
      {isMobile ? (
        /* Mobile / Small Screen Layout (< 1024px) */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Segmented Control */}
          <div className="flex items-center justify-around border-b border-border bg-background-secondary p-1 text-xs">
            <button
              onClick={() => setMobileView('editor')}
              className={`flex-1 py-1.5 font-medium rounded transition ${
                mobileView === 'editor'
                  ? 'bg-background shadow-sm text-accent'
                  : 'text-foreground-muted'
              }`}
            >
              Editor
            </button>
            <button
              onClick={() => setMobileView('inspector')}
              className={`flex-1 py-1.5 font-medium rounded transition ${
                mobileView === 'inspector'
                  ? 'bg-background shadow-sm text-accent'
                  : 'text-foreground-muted'
              }`}
            >
              Inspector
            </button>
            <button
              onClick={() => setMobileView('problems')}
              className={`flex-1 py-1.5 font-medium rounded transition ${
                mobileView === 'problems'
                  ? 'bg-background shadow-sm text-accent'
                  : 'text-foreground-muted'
              }`}
            >
              Problems
            </button>
          </div>

          <div className="flex-1 overflow-hidden">
            {mobileView === 'editor' && <MiniLangEditor />}
            {mobileView === 'inspector' && (
              <div className="h-full flex flex-col">
                <Tabs />
                <div className="flex-1 overflow-hidden">{renderActivePanel()}</div>
              </div>
            )}
            {mobileView === 'problems' && <ProblemsPanel />}
          </div>
        </div>
      ) : (
        /* Desktop Layout (>= 1024px) */
        <div className="flex-1 overflow-hidden">
          <PanelGroup direction="horizontal">
            {/* Left: MiniLang Code Editor */}
            <Panel defaultSize={50} minSize={25} className="flex flex-col">
              <div className="px-3 py-1.5 border-b border-border bg-background-secondary/50 text-[11px] font-semibold text-foreground-muted uppercase tracking-wider flex items-center justify-between">
                <span>MiniLang Source</span>
                <span className="font-mono text-[10px] text-foreground-muted/70">
                  hello.mini
                </span>
              </div>
              <div className="flex-1 overflow-hidden">
                <MiniLangEditor />
              </div>
            </Panel>

            <PanelResizeHandle className="w-1.5 bg-border hover:bg-accent cursor-col-resize resize-handle transition-colors" />

            {/* Right: Tabbed Inspector Panels */}
            <Panel defaultSize={50} minSize={30} className="flex flex-col">
              <Tabs />
              <div className="flex-1 overflow-hidden">{renderActivePanel()}</div>
            </Panel>
          </PanelGroup>
        </div>
      )}

      <StatusBar />
      <HelpModal />
    </div>
  );
};
