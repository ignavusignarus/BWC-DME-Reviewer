import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';
import { _resetCachedBaseForTests } from '../../api.js';

beforeEach(() => {
    _resetCachedBaseForTests();
    globalThis.fetch = vi.fn();
});

const TRANSCRIPT = {
    schema_version: '1.0',
    source: { path: '/x/y.mp3', duration_seconds: 60.0 },
    speakers: [],
    segments: [
        { id: 0, start: 1.0, end: 4.0, text: 'Hello world', words: [], low_confidence: false },
    ],
};
const SPEECH_SEGMENTS = [{ start: 1.0, end: 4.0 }];

function mockTranscriptOk() {
    fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ transcript: TRANSCRIPT, speech_segments: SPEECH_SEGMENTS }),
    });
}

describe('ReviewerView', () => {
    it('fetches transcript on mount and renders the source name', async () => {
        mockTranscriptOk();
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'dme' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => expect(screen.getByText(/Hello world/)).toBeDefined());
    });

    it('shows an error message if fetch fails', async () => {
        fetch.mockResolvedValueOnce({ ok: false, status: 500 });
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'dme' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => expect(screen.getByText(/failed to load transcript/i)).toBeDefined());
    });

    it('renumbers transcript segment IDs sequentially', async () => {
        // Older cached transcripts (and faster-whisper VAD-filtered output)
        // have id=0 on every segment. The renderer must renumber them so the
        // auto-scroll DOM lookup can find the active segment.
        fetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve({
                transcript: {
                    ...TRANSCRIPT,
                    segments: [
                        { id: 0, start: 0, end: 1, text: 'a', words: [], low_confidence: false },
                        { id: 0, start: 1, end: 2, text: 'b', words: [], low_confidence: false },
                        { id: 0, start: 2, end: 3, text: 'c', words: [], low_confidence: false },
                    ],
                },
                speech_segments: SPEECH_SEGMENTS,
            }),
        });
        const { container } = render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'dme' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => expect(screen.getByText('c')).toBeDefined());
        const ids = Array.from(container.querySelectorAll('[data-segment-id]')).map(e => e.getAttribute('data-segment-id'));
        expect(ids).toEqual(['0', '1', '2']);
    });
});
