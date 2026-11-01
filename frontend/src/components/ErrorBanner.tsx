import React from 'react';
import { useNexora } from '../store/useNexora';
import { AlertCircle, RotateCcw, X } from 'lucide-react';

export const ErrorBanner: React.FC = () => {
  const { apiError, dismissApiError, compile } = useNexora();

  if (!apiError) return null;

  return (
    <div className="bg-error-bg border-b border-error-border text-error px-4 py-2 flex items-center justify-between text-xs z-30 animate-in fade-in slide-in-from-top-1 duration-200">
      <div className="flex items-center gap-2">
        <AlertCircle className="w-4 h-4 shrink-0 text-error" />
        <span className="font-semibold">[{apiError.code}]</span>
        <span>{apiError.message}</span>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => compile(false)}
          className="flex items-center gap-1 font-medium hover:underline text-xs"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Retry</span>
        </button>

        <button
          onClick={dismissApiError}
          className="p-0.5 rounded hover:bg-error/10 transition"
          title="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
