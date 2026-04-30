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

    it('shows current and total time', () => {
        render(withCtx({ ...baseCtx, currentTime: 65, duration: 3600 }, <Transport />));
        expect(screen.getByText('01:05 / 60:00')).toBeDefined();
    });

    it('±5 s skip respects duration bounds', () => {
        const seekTo = vi.fn();
        render(withCtx({ ...baseCtx, seekTo, currentTime: 3, duration: 60 }, <Transport />));
        fireEvent.click(screen.getByRole('button', { name: /skip back/i }));
        expect(seekTo).toHaveBeenCalledWith(0);  // clamped at 0
    });
});
