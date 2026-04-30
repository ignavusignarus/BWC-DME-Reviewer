import { describe, it, expect } from 'vitest';
import { computeCells } from './useTimelineGeometry.js';

const SEGMENTS = [
    { start: 0, end: 5 },
    { start: 10, end: 15 },
    { start: 20, end: 25 },
];

describe('computeCells', () => {
    it('returns interleaved speech and silence cells', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, expandedSilenceIndex: null });
        // Expected: speech, silence, speech, silence, speech, silence (no leading silence since first segment starts at 0)
        expect(cells.length).toBe(6);
        expect(cells.map(c => c.kind)).toEqual(['speech', 'silence', 'speech', 'silence', 'speech', 'silence']);
    });

    it('uncompressed widths are proportional to duration', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, expandedSilenceIndex: null });
        const firstSpeech = cells.find(c => c.kind === 'speech');
        expect(firstSpeech.widthPctUncompressed).toBeCloseTo((5 / 30) * 100, 5);
    });

    it('collapsed widths sum to ~100% (always fits container)', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, expandedSilenceIndex: null });
        const total = cells.reduce((s, c) => s + c.widthPctCollapsed, 0);
        expect(total).toBeCloseTo(100, 1);
    });

    it('collapsed mode allocates ~25% of width to silence by default', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, expandedSilenceIndex: null });
        const silenceTotal = cells
            .filter(c => c.kind === 'silence')
            .reduce((s, c) => s + c.widthPctCollapsed, 0);
        // 25% of width for silences (within rounding).
        expect(silenceTotal).toBeCloseTo(25, 0);
    });

    it('expanded silence cell gets a larger share', () => {
        const cells = computeCells({ speechSegments: SEGMENTS, durationSeconds: 30, expandedSilenceIndex: 1 });
        const silenceCells = cells.filter(c => c.kind === 'silence');
        // The expanded cell (index 1) should be wider than the others.
        expect(silenceCells[1].widthPctCollapsed).toBeGreaterThan(silenceCells[0].widthPctCollapsed);
        expect(silenceCells[1].widthPctCollapsed).toBeGreaterThan(silenceCells[2].widthPctCollapsed);
    });

    it('omits zero-duration leading silence', () => {
        const cells = computeCells({ speechSegments: [{ start: 0, end: 5 }], durationSeconds: 5, expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['speech']);
    });

    it('emits trailing silence when last segment ends before duration', () => {
        const cells = computeCells({ speechSegments: [{ start: 0, end: 5 }], durationSeconds: 30, expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['speech', 'silence']);
        expect(cells[1].endSec).toBe(30);
    });

    it('emits leading silence when first segment starts after 0', () => {
        const cells = computeCells({ speechSegments: [{ start: 5, end: 10 }], durationSeconds: 15, expandedSilenceIndex: null });
        expect(cells.map(c => c.kind)).toEqual(['silence', 'speech', 'silence']);
        expect(cells[0].startSec).toBe(0);
        expect(cells[0].endSec).toBe(5);
    });

    it('many silence cells still fit in 100% (clamped to min width)', () => {
        // 200 short speech segments, ~200 silence intervals between them.
        const segs = [];
        for (let i = 0; i < 200; i++) segs.push({ start: i * 10, end: i * 10 + 1 });
        const cells = computeCells({ speechSegments: segs, durationSeconds: 2000, expandedSilenceIndex: null });
        const total = cells.reduce((s, c) => s + c.widthPctCollapsed, 0);
        expect(total).toBeLessThanOrEqual(100.5);
    });
});
