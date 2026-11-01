import React, { useEffect } from 'react';
import { useNexora } from '../store/useNexora';
import { X, Keyboard, BookOpen, Code } from 'lucide-react';

export const HelpModal: React.FC = () => {
  const { showHelp, setShowHelp } = useNexora();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        // If not typing in input
        const target = e.target as HTMLElement;
        if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
          e.preventDefault();
          setShowHelp(!showHelp);
        }
      }
      if (e.key === 'Escape' && showHelp) {
        setShowHelp(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showHelp, setShowHelp]);

  if (!showHelp) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-150">
      <div className="w-full max-w-2xl bg-background border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-border bg-background-secondary flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-accent" />
            <h3 className="text-sm font-semibold text-foreground">
              Nexora Playground Reference & Shortcuts
            </h3>
          </div>
          <button
            onClick={() => setShowHelp(false)}
            className="p-1 rounded-md text-foreground-muted hover:text-foreground hover:bg-background-tertiary transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-auto space-y-5 text-xs">
          {/* Shortcuts */}
          <div>
            <div className="flex items-center gap-1.5 font-semibold text-foreground mb-2">
              <Keyboard className="w-4 h-4 text-accent" />
              <span>Keyboard Shortcuts</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 rounded bg-background-secondary border border-border flex items-center justify-between">
                <span className="text-foreground-muted">Compile Source</span>
                <kbd className="px-2 py-0.5 rounded bg-background border border-border font-mono font-medium">
                  Ctrl / ⌘ + Enter
                </kbd>
              </div>
              <div className="p-2 rounded bg-background-secondary border border-border flex items-center justify-between">
                <span className="text-foreground-muted">Run Sandbox</span>
                <kbd className="px-2 py-0.5 rounded bg-background border border-border font-mono font-medium">
                  Ctrl / ⌘ + Shift + Enter
                </kbd>
              </div>
              <div className="p-2 rounded bg-background-secondary border border-border flex items-center justify-between">
                <span className="text-foreground-muted">Toggle Comment</span>
                <kbd className="px-2 py-0.5 rounded bg-background border border-border font-mono font-medium">
                  Ctrl / ⌘ + /
                </kbd>
              </div>
              <div className="p-2 rounded bg-background-secondary border border-border flex items-center justify-between">
                <span className="text-foreground-muted">Toggle Help</span>
                <kbd className="px-2 py-0.5 rounded bg-background border border-border font-mono font-medium">
                  ? / Esc
                </kbd>
              </div>
            </div>
          </div>

          {/* MiniLang Grammar Summary */}
          <div>
            <div className="flex items-center gap-1.5 font-semibold text-foreground mb-2">
              <Code className="w-4 h-4 text-accent" />
              <span>MiniLang Syntax Cheatsheet</span>
            </div>
            <div className="bg-background-secondary border border-border rounded-lg p-3 font-mono text-[11px] leading-relaxed space-y-2">
              <div>
                <span className="text-purple-400 font-semibold">// Variable declarations</span>
                <br />
                make count: int = 10;
                <br />
                make price = 19.99; <span className="text-foreground-muted">// Inferred as float</span>
              </div>

              <div>
                <span className="text-purple-400 font-semibold">// Functions (Tasks)</span>
                <br />
                task add(a: int, b: int): int &#123;
                <br />
                &nbsp;&nbsp;give a + b;
                <br />
                &#125;
              </div>

              <div>
                <span className="text-purple-400 font-semibold">// Conditionals & Loops</span>
                <br />
                when (count &gt;= 10 both count &lt; 20) &#123;
                <br />
                &nbsp;&nbsp;show("In range");
                <br />
                &#125; otherwise &#123;
                <br />
                &nbsp;&nbsp;show("Outside");
                <br />
                &#125;
                <br />
                <br />
                during (count &gt; 0) &#123;
                <br />
                &nbsp;&nbsp;count = count - 1;
                <br />
                &#125;
              </div>

              <div>
                <span className="text-purple-400 font-semibold">// Logical operators:</span>
                <span className="text-foreground ml-2">
                  either (OR), both (AND), not (NOT), yes (true), no (false)
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-border bg-background-secondary text-right">
          <button
            onClick={() => setShowHelp(false)}
            className="px-4 py-1.5 rounded bg-accent hover:bg-accent-hover text-accent-text text-xs font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
