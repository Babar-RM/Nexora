import { describe, it, expect, beforeEach } from 'vitest';
import { useNexora } from '../store/useNexora';

describe('Nexora Zustand Store (RFC-0010 §3.4)', () => {
  beforeEach(() => {
    // Reset store state
    useNexora.setState({
      source: 'make x = 10;',
      phase: 'idle',
      result: null,
      stale: false,
      apiError: null,
      selection: null,
      activeTab: 'output',
      theme: 'dark',
    });
  });

  it('updates source and sets stale to true on edit', () => {
    expect(useNexora.getState().stale).toBe(false);
    useNexora.getState().setSource('make x = 20;');
    expect(useNexora.getState().source).toBe('make x = 20;');
    expect(useNexora.getState().stale).toBe(true);
  });

  it('updates selection range for cross-highlighting', () => {
    useNexora.getState().selectRange({
      startLine: 3,
      startColumn: 5,
      endLine: 3,
      endColumn: 12,
    });

    expect(useNexora.getState().selection).toEqual({
      startLine: 3,
      startColumn: 5,
      endLine: 3,
      endColumn: 12,
    });

    useNexora.getState().selectRange(null);
    expect(useNexora.getState().selection).toBeNull();
  });

  it('updates active tab', () => {
    useNexora.getState().setActiveTab('ast');
    expect(useNexora.getState().activeTab).toBe('ast');

    useNexora.getState().setActiveTab('problems');
    expect(useNexora.getState().activeTab).toBe('problems');
  });

  it('updates theme and documentElement class', () => {
    useNexora.getState().setTheme('light');
    expect(useNexora.getState().theme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    useNexora.getState().setTheme('dark');
    expect(useNexora.getState().theme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('handles API error dismissal', () => {
    useNexora.setState({
      apiError: { code: 'network_error', message: 'Failed to connect' },
    });
    expect(useNexora.getState().apiError).not.toBeNull();

    useNexora.getState().dismissApiError();
    expect(useNexora.getState().apiError).toBeNull();
  });
});
