import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import Timeline from './Timeline.jsx';

const SEGS = [{ start: 0, end: 5 }, { start: 10, end: 15 }];

function withCtx(currentTime, ui, seekToFn) {
    return <ReviewerContext.Provider value={{
        audioRef: { current: null }, currentTime, duration: 20, playing: false,
        play: () => {}, pause: () => {}, seekTo: seekToFn || vi.fn(),
        folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
    }}>{ui}</ReviewerContext.Provider>;
}

describe('Timeline', () => {
    it('renders collapsed view by default', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        expect(screen.getByTestId('timeline-collapsed')).toBeDefined();
        expect(screen.queryByTestId('timeline-uncompressed')).toBeNull();
    });

    it('toggle button switches to uncompressed', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        const toggle = screen.getByRole('button', { name: /uncompressed/i });
        fireEvent.click(toggle);
        expect(screen.getByTestId('timeline-uncompressed')).toBeDefined();
        expect(screen.queryByTestId('timeline-collapsed')).toBeNull();
    });

    it('clicking a speech cell calls seekTo', () => {
        const seekTo = vi.fn();
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />, seekTo));
        const cells = screen.getAllByTestId('seg-cell');
        // Mock getBoundingClientRect for the first cell
        const rect = { left: 0, width: 100, top: 0, height: 20, right: 100, bottom: 20, x: 0, y: 0, toJSON: () => ({}) };
        cells[0].getBoundingClientRect = () => rect;
        // Click at the right edge of the first cell (full width = 5 seconds)
        fireEvent.click(cells[0], { clientX: 100 });
        expect(seekTo).toHaveBeenCalledWith(5);
    });

    it('clicking a silence bar expands it; second click collapses it', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        const silences = screen.getAllByTestId('silence-cell');
        // Initial widths via inline style — we can read flex value or width
        const initial = silences[0].style.flex;
        fireEvent.click(silences[0]);
        expect(silences[0].style.flex).not.toBe(initial);  // expanded
        fireEvent.click(silences[0]);
        expect(silences[0].style.flex).toBe(initial);  // collapsed
    });

    it('Esc collapses an expanded silence', () => {
        render(withCtx(0, <Timeline speechSegments={SEGS} duration={20} searchMatches={[]} />));
        const silences = screen.getAllByTestId('silence-cell');
        const initial = silences[0].style.flex;
        fireEvent.click(silences[0]);
        expect(silences[0].style.flex).not.toBe(initial);
        fireEvent.keyDown(window, { key: 'Escape' });
        expect(silences[0].style.flex).toBe(initial);
    });
});
