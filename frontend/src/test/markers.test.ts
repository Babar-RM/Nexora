import { describe, it, expect, vi } from 'vitest';
import { updateMarkers } from '../editor/markers';
import type { DiagnosticItem } from '../api/schema';

describe('Monaco Markers converter (RFC-0010 §3.7)', () => {
  it('converts error diagnostics to Monaco markers with hints', () => {
    let capturedMarkers: any[] = [];

    const mockMonaco: any = {
      MarkerSeverity: {
        Error: 8,
        Warning: 4,
      },
      editor: {
        setModelMarkers: vi.fn((_model, _owner, markers) => {
          capturedMarkers = markers;
        }),
      },
    };

    const mockModel: any = {};
    const mockEditorInstance: any = {
      getModel: () => mockModel,
    };

    const diagnostics: DiagnosticItem[] = [
      {
        phase: 'semantic',
        code: 'E3001',
        line: 4,
        column: 6,
        length: 5,
        message: "use of undeclared variable 'total'",
        hint: "Declare 'total' with 'make total = ...;' before using it.",
      },
      {
        phase: 'semantic',
        code: 'W4003',
        line: 2,
        column: 6,
        length: 1,
        message: "unused variable 'x'",
        hint: null,
      },
    ];

    updateMarkers(mockMonaco, mockEditorInstance, diagnostics);

    expect(mockMonaco.editor.setModelMarkers).toHaveBeenCalledTimes(1);
    expect(capturedMarkers.length).toBe(2);

    // Verify Error diagnostic
    const errMarker = capturedMarkers[0];
    expect(errMarker.severity).toBe(8); // Error
    expect(errMarker.startLineNumber).toBe(4);
    expect(errMarker.startColumn).toBe(6);
    expect(errMarker.endColumn).toBe(11); // 6 + 5
    expect(errMarker.message).toContain('[E3001]');
    expect(errMarker.message).toContain("Hint: Declare 'total'");

    // Verify Warning diagnostic
    const warnMarker = capturedMarkers[1];
    expect(warnMarker.severity).toBe(4); // Warning
    expect(warnMarker.startLineNumber).toBe(2);
    expect(warnMarker.startColumn).toBe(6);
    expect(warnMarker.endColumn).toBe(7); // 6 + 1
    expect(warnMarker.message).toContain('[W4003]');
  });
});
