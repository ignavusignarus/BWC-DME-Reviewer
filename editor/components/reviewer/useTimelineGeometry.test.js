import { describe, it, expect } from 'vitest';
import { computeCells } from './useTimelineGeometry.js';

const SEGMENTS = [
    { start: 0, end: 5 },
    { start: 10, end: 15 },
    { start: 20, end: 25 },
];

describe('computeCells', () => {
    it('returns interleaved speech and silence cells (collapsed mode)', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'collapsed', expandedSilenceIndex: null });
        // Expected: speech, silence, speech, silence, speech, silence (no leading silence since first segment starts at 0)
        expect(cells.length).toBe(6);
        expect(cells.map(c => c.kind)).toEqual(['speech', 'silence', 'speech', 'silence', 'speech', 'silence']);
    });

    it('uncompressed mode gives widthPct proportional to duration', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'uncompressed', expandedSilenceIndex: null });
        // First speech cell: 5 of 30 seconds = 16.67%
        const firstSpeech = cells.find(c => c.kind === 'speech');
        expect(firstSpeech.widthPct).toBeCloseTo((5 / 30) * 100, 5);
    });

    it('expanded silence index produces 80px width on the matching silence', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, mode: 'collapsed', expandedSilenceIndex: 1 });
        const silenceCells = cells.filter(c => c.kind === 'silence');
        // index 1 of silence cells (0-indexed) gets the 80px width
        expect(silenceCells[1].widthPx).toBe(80);
        expect(silenceCells[0].widthPx).toBe(24);
    });

    it('omits zero-duration leading silence', () => {
        const cells = computeCells({ speechSegments: [{ start: 0, end: 5 }], durationSeconds: 5, mode: 'collapsed', expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['speech']);
    });

    it('emits trailing silence when last segment ends before duration', () => {
        const cells = computeCells({ speechSegments: [{ start: 0, end: 5 }], durationSeconds: 30, mode: 'collapsed', expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['speech', 'silence']);
        expect(cells[1].endSec).toBe(30);
    });

    it('emits leading silence when first segment starts after 0', () => {
        const cells = computeCells({ speechSegments: [{ start: 5, end: 10 }], durationSeconds: 15, mode: 'collapsed', expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['silence', 'speech', 'silence']);
        expect(cells[0].startSec).toBe(0);
        expect(cells[0].endSec).toBe(5);
    });
});
