import { describe, it, expect } from 'vitest';
import { encodeSource, decodeSource } from '../lib/share';

describe('Share URL hash encoder/decoder (RFC-0010 §3.5)', () => {
  it('encodes and decodes source code accurately round-trip', () => {
    const code = 'task add(x: int, y: int): int {\n    give x + y;\n}\nshow(add(2, 3));';
    const encoded = encodeSource(code);
    expect(encoded).toBeTypeOf('string');
    expect(encoded.length).toBeGreaterThan(0);

    const hash = `#src=${encoded}`;
    const decoded = decodeSource(hash);
    expect(decoded).toBe(code);
  });

  it('handles source with special characters, unicode, and quotes', () => {
    const code = 'show("Hello, world! 123 <= 456 && % / \\n");';
    const encoded = encodeSource(code);
    const decoded = decodeSource(`src=${encoded}`);
    expect(decoded).toBe(code);
  });

  it('rejects programs exceeding the 8 KB limit', () => {
    const oversized = 'a'.repeat(9000);
    expect(() => encodeSource(oversized)).toThrow('Program is too large to share via link');
  });

  it('gracefully returns null on invalid or corrupted hash', () => {
    expect(decodeSource('')).toBeNull();
    expect(decodeSource('#invalid=123')).toBeNull();
    expect(decodeSource('#src=!!!corrupt_base64!!!')).toBeNull();
  });
});
