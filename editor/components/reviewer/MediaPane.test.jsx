import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import MediaPane from './MediaPane.jsx';

function withCtx(source, ui) {
    return (
        <ReviewerContext.Provider value={{
            audioRef: { current: null }, currentTime: 0, duration: 0, playing: false,
            play: () => {}, pause: () => {}, seekTo: () => {},
            folder: '/x', source,
        }}>
            {ui}
        </ReviewerContext.Provider>
    );
}

const NOOP_HANDLERS = {
    onTimeUpdate: () => {}, onLoadedMetadata: () => {},
    onPlay: () => {}, onPause: () => {},
};

describe('MediaPane', () => {
    it('renders audio mode with waveform placeholder + transport', () => {
        render(withCtx({ path: '/x/y.mp3', mode: 'audio' }, <MediaPane {...NOOP_HANDLERS} />));
        expect(screen.getByRole('toolbar')).toBeDefined();
        expect(screen.queryByTestId('video-element')).toBeNull();
        expect(screen.getByTestId('waveform-placeholder')).toBeDefined();
    });

    it('renders video mode with <video> element pointing at /api/source/video', () => {
        render(withCtx({ path: '/x/y.mp4', mode: 'video' }, <MediaPane {...NOOP_HANDLERS} />));
        const video = screen.getByTestId('video-element');
        expect(video).toBeDefined();
        expect(video.getAttribute('src')).toMatch(/\/api\/source\/video/);
        // No waveform in video mode
        expect(screen.queryByTestId('waveform-placeholder')).toBeNull();
    });
});
