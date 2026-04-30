import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import Transport from './Transport.jsx';

function withCtx(ctx, ui) {
    return <ReviewerContext.Provider value={ctx}>{ui}</ReviewerContext.Provider>;
}

const baseCtx = {
    audioRef: { current: null },
    play: vi.fn(),
    pause: vi.fn(),
    seekTo: vi.fn(),
    playing: false,
    currentTime: 0,
    duration: 60,
    folder: '/x',
    source: { path: '/x/y.mp3', mode: 'audio' },
};

describe('Transport', () => {
    it('play button calls play()', () => {
        const play = vi.fn();
        render(withCtx({ ...baseCtx, play }, <Transport />));
        fireEvent.click(screen.getByRole('button', { name: /^play$/i }));
        expect(play).toHaveBeenCalled();
    });

    it('shows current and total time (under 1 hour: mm:ss)', () => {
        render(withCtx({ ...baseCtx, currentTime: 65, duration: 1800 }, <Transport />));
        expect(screen.getByText('01:05 / 30:00')).toBeDefined();
    });

    it('shows hours when duration is >= 1 hour', () => {
        render(withCtx({ ...baseCtx, currentTime: 3725, duration: 7200 }, <Transport />));
        expect(screen.getByText('1:02:05 / 2:00:00')).toBeDefined();
    });

    it('±5 s skip respects duration bounds', () => {
        const seekTo = vi.fn();
        render(withCtx({ ...baseCtx, seekTo, currentTime: 3, duration: 60 }, <Transport />));
        fireEvent.click(screen.getByRole('button', { name: /skip back/i }));
        expect(seekTo).toHaveBeenCalledWith(0);  // clamped at 0
    });
});
