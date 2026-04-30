import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import TranscriptPanel from './TranscriptPanel.jsx';

const TRANSCRIPT = {
    segments: [
        { id: 0, start: 0.0, end: 4.0, text: 'Hello world', words: [], low_confidence: false },
        { id: 1, start: 4.0, end: 8.0, text: 'Second utterance', words: [{ word: 'Second', score: 0.4, start: 4.0, end: 4.5 }, { word: 'utterance', score: 0.9, start: 4.5, end: 5.0 }], low_confidence: true },
        { id: 2, start: 8.0, end: 12.0, text: 'Third', words: [], low_confidence: false },
    ],
};

function withCtx(currentTime, ui, seekToFn) {
    return <ReviewerContext.Provider value={{
        audioRef: { current: null }, currentTime, duration: 12, playing: false,
        play: () => {}, pause: () => {}, seekTo: seekToFn || vi.fn(),
        folder: '/x', source: { path: '/x/y.mp3', mode: 'audio' },
    }}>{ui}</ReviewerContext.Provider>;
}

describe('TranscriptPanel', () => {
    it('renders all segments', () => {
        render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        expect(screen.getByText('Hello world')).toBeDefined();
        expect(screen.getByText(/Third/)).toBeDefined();
    });

    it('marks the active utterance based on currentTime', () => {
        const { container } = render(withCtx(5.0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        const active = container.querySelector('[data-active="true"]');
        expect(active).toBeTruthy();
        expect(active.textContent).toContain('Second utterance');
    });

    it('clicking a segment calls seekTo', () => {
        const seekTo = vi.fn();
        render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />, seekTo));
        // Find the segment containing "Third" and click it
        const thirdSegment = screen.getByText(/Third/).closest('[data-segment-id]');
        fireEvent.click(thirdSegment);
        expect(seekTo).toHaveBeenCalledWith(8.0);
    });

    it('underlines low-score words', () => {
        const { container } = render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="" />));
        const underlined = container.querySelectorAll('[data-low-conf="true"]');
        expect(underlined.length).toBeGreaterThan(0);
    });

    it('highlights search matches', () => {
        const { container } = render(withCtx(0, <TranscriptPanel transcript={TRANSCRIPT} searchQuery="utterance" />));
        const marks = container.querySelectorAll('mark');
        expect(marks.length).toBe(1);
        expect(marks[0].textContent).toBe('utterance');
    });
});
