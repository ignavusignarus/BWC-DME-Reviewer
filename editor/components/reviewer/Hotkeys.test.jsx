import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';
import { _resetCachedBaseForTests } from '../../api.js';

beforeEach(() => {
    _resetCachedBaseForTests();
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
            transcript: { source: { path: '/x/y.mp3', duration_seconds: 60 }, speakers: [], segments: [] },
            speech_segments: [],
        }),
    }));
});

function renderReviewer() {
    return render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'dme' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} onSelectSource={() => {}} />);
}

describe('hotkeys', () => {
    it('Space toggles play (calls play when paused)', async () => {
        renderReviewer();
        await waitFor(() => screen.getByTestId('mediapane'));
        const audio = document.querySelector('audio,video');
        if (!audio) throw new Error('No media element');
        const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();
        fireEvent.keyDown(window, { key: ' ', code: 'Space' });
        expect(playSpy).toHaveBeenCalled();
    });

    it('keys absorbed when an input is focused', async () => {
        renderReviewer();
        await waitFor(() => screen.getByTestId('mediapane'));
        const audio = document.querySelector('audio,video');
        const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();
        const search = screen.getByPlaceholderText(/search/i);
        search.focus();
        fireEvent.keyDown(search, { key: ' ', code: 'Space', target: search });
        // Handler bails on INPUT/TEXTAREA tag check; play should NOT be called.
        expect(playSpy).not.toHaveBeenCalled();
    });

    it('Ctrl+S preventDefault is called (no-op in M6 but must not save page)', async () => {
        renderReviewer();
        await waitFor(() => screen.getByTestId('mediapane'));
        const evt = new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true, cancelable: true });
        const spy = vi.spyOn(evt, 'preventDefault');
        window.dispatchEvent(evt);
        expect(spy).toHaveBeenCalled();
    });

    it('Slash focuses the search input', async () => {
        renderReviewer();
        await waitFor(() => screen.getByTestId('mediapane'));
        const evt = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true });
        const spy = vi.spyOn(evt, 'preventDefault');
        window.dispatchEvent(evt);
        const search = screen.getByPlaceholderText(/search/i);
        expect(document.activeElement).toBe(search);
        expect(spy).toHaveBeenCalled();
    });
});
