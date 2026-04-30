import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ReviewerView from './ReviewerView.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
            transcript: { source: { path: '/x/y.mp3', duration_seconds: 60 }, speakers: [], segments: [] },
            speech_segments: [],
        }),
    }));
});

function renderReviewer() {
    return render(<ReviewerView folder="/x" source={{ path: '/x/y.mp3', mode: 'audio' }} onBack={() => {}} manifest={{ folder: '/x', files: [] }} onSelectSource={() => {}} />);
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

    it('letter keys absorbed when textarea is focused', async () => {
        renderReviewer();
        await waitFor(() => screen.getByTestId('mediapane'));
        const audio = document.querySelector('audio,video');
        const playSpy = vi.spyOn(audio, 'play').mockResolvedValue();
        // Focus the names textarea (rendered by ContextNamesPanel)
        const namesArea = screen.getByLabelText(/^names$/i);
        namesArea.focus();
        fireEvent.keyDown(namesArea, { key: ' ', code: 'Space', target: namesArea });
        // Window keydown still fires (event propagates), but the handler should bail
        // due to tag check; play should NOT be called.
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
        // The search input should be the active element
        const search = screen.getByPlaceholderText(/search/i);
        expect(document.activeElement).toBe(search);
        expect(spy).toHaveBeenCalled();
    });
});
