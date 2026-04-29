import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

const SAMPLE_MANIFEST = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'officer.mp4', path: 'C:/case-folder/officer.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
    ],
};

function setupFetchStub({ initialStatus = 'idle', sequence = [] } = {}) {
    let stateCalls = 0;
    return vi.fn((url, opts) => {
        if (url.endsWith('/api/project/open')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(SAMPLE_MANIFEST) });
        }
        if (url.endsWith('/api/source/process')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'queued' }) });
        }
        if (url.includes('/api/source/state')) {
            const next = sequence[stateCalls] ?? sequence[sequence.length - 1] ?? initialStatus;
            stateCalls += 1;
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: next }) });
        }
        return Promise.reject(new Error('unexpected url: ' + url));
    });
}

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        vi.useFakeTimers();
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
            pickFolder: vi.fn(() => Promise.resolve('C:/case-folder')),
        };
    });

    afterEach(() => {
        vi.useRealTimers();
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the empty state on mount', () => {
        global.fetch = setupFetchStub();
        render(<EditorApp />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('opens a folder, renders project view', async () => {
        global.fetch = setupFetchStub();
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
    });

    it('kicks off processing on file select', async () => {
        global.fetch = setupFetchStub({ sequence: ['queued', 'running', 'completed'] });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());

        fireEvent.click(screen.getByText('officer.mp4'));

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith(
                'http://127.0.0.1:8888/api/source/process',
                expect.objectContaining({
                    method: 'POST',
                    body: JSON.stringify({ folder: 'C:/case-folder', source: 'C:/case-folder/officer.mp4' }),
                }),
            );
        });
    });

    it('polls source state and updates UI to completed', async () => {
        global.fetch = setupFetchStub({ sequence: ['running', 'running', 'completed'] });
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => expect(screen.getByText('officer.mp4')).toBeDefined());
        fireEvent.click(screen.getByText('officer.mp4'));

        // First poll → running
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        // Second poll → completed
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });
        await act(async () => {
            await vi.advanceTimersByTimeAsync(1000);
        });

        await waitFor(() => {
            const row = document.querySelector('[data-status="completed"]');
            expect(row).not.toBeNull();
        });
    });
});
