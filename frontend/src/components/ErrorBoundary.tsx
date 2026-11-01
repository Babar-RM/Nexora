import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="h-full flex flex-col items-center justify-center p-6 text-center bg-background text-foreground">
          <AlertTriangle className="w-10 h-10 text-error mb-3" />
          <h3 className="text-sm font-semibold text-foreground mb-1">
            {this.props.fallbackTitle || 'Panel Rendering Error'}
          </h3>
          <p className="text-xs text-foreground-muted max-w-sm mb-4">
            {this.state.error?.message || 'An unexpected error occurred while rendering this panel.'}
          </p>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-accent hover:bg-accent-hover text-accent-text text-xs font-medium transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Reload Panel</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
