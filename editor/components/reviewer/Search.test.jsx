import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';
import { _resetCachedBaseForTests } from '../../api.js';

const TRANSCRIPT = {
    source: { path: '/x/y.mp3', duration_seconds: 30 },
    speakers: [],
    segments: [
        { id: 0, start: 0, end: 5, text: 'medication first', words: [], low_confidence: false },
        { id: 1, start: 10, end: 15, text: 'second utterance', words: [], low_confidence: false },
        { id: 2, start: 20, end: 25, text: 'medication third', words: [], low_confidence: false },
    ],
};
const SPEECH_SEGMENTS = [{ start: 0, end: 5 }, { start: 10, end: 15 }, { start: 20, end: 25 }];

function mockTranscriptOk() {
    fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ transcript: TRANSCRIPT, speech_segments: SPEECH_SEGMENTS }),
    });
}

beforeEach(() => {
    _resetCachedBaseForTests();
    globalThis.fetch = vi.fn();
    mockTranscriptOk();
});

afterEach(() => {
    vi.useRealTimers();
});

describe('search', () => {
    it('renders the search input', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));
        const input = screen.getByPlaceholderText(/search/i);
        expect(input).toBeDefined();
    });

    it('debounced 100 ms; finds case-insensitive matches', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));

        const input = screen.getByPlaceholderText(/search/i);
        fireEvent.change(input, { target: { value: 'MEDICATION' } });

        // waitFor polls until the debounce fires (100 ms) and marks appear
        await waitFor(
            () => {
                const marks = document.querySelectorAll('mark');
                expect(marks.length).toBe(2);
            },
            { timeout: 500 }
        );
    });

    it('shows match count after debounce', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));

        const input = screen.getByPlaceholderText(/search/i);
        fireEvent.change(input, { target: { value: 'medication' } });

        await waitFor(
            () => {
                const matchText = screen.getByText(/2 matches/i);
                expect(matchText).toBeDefined();
            },
            { timeout: 500 }
        );
    });

    it('shows no match count label when query is empty', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));

        // No query — the match count span should not be present
        const matchText = screen.queryByText(/matches/i);
        expect(matchText).toBeNull();
    });

    it('clears highlights when query is cleared', async () => {
        render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} />);
        await waitFor(() => screen.getByText(/medication first/));

        const input = screen.getByPlaceholderText(/search/i);
        fireEvent.change(input, { target: { value: 'medication' } });
        await waitFor(() => expect(document.querySelectorAll('mark').length).toBe(2), { timeout: 500 });

        // Clear the query
        fireEvent.change(input, { target: { value: '' } });
        await waitFor(() => expect(document.querySelectorAll('mark').length).toBe(0), { timeout: 500 });
    });
});
