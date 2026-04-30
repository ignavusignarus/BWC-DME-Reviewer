import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReviewerContext } from './ReviewerContext.js';
import MediaPane from './MediaPane.jsx';

function withCtx(source, ui, engineBase = 'http://127.0.0.1:0') {
    return (
        <ReviewerContext.Provider value={{
            audioRef: { current: null }, currentTime: 0, duration: 0, playing: false,
            play: () => {}, pause: () => {}, seekTo: () => {},
            folder: '/x', source, engineBase,
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
    it('renders DME mode with waveform placeholder + transport', () => {
        render(withCtx({ path: '/x/y.mp3', mode: 'dme' }, <MediaPane {...NOOP_HANDLERS} />));
        expect(screen.getByRole('toolbar')).toBeDefined();
        expect(screen.queryByTestId('video-element')).toBeNull();
        expect(screen.getByTestId('waveform-container')).toBeDefined();
    });

    it('renders BWC mode with <video> element pointing at /api/source/video', () => {
        render(withCtx({ path: '/x/y.mp4', mode: 'bwc' }, <MediaPane {...NOOP_HANDLERS} />));
        const video = screen.getByTestId('video-element');
        expect(video).toBeDefined();
        expect(video.getAttribute('src')).toMatch(/\/api\/source\/video/);
        // No waveform in video mode
        expect(screen.queryByTestId('waveform-container')).toBeNull();
    });

    it('prefixes media URL with engineBase from context', () => {
        render(withCtx({ path: '/x/y.mp4', mode: 'bwc' }, <MediaPane {...NOOP_HANDLERS} />, 'http://127.0.0.1:9999'));
        const video = screen.getByTestId('video-element');
        expect(video.getAttribute('src')).toMatch(/^http:\/\/127\.0\.0\.1:9999\/api\/source\/video/);
    });
});
