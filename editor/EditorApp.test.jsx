import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

const SAMPLE_MANIFEST = {
    folder: 'C:/case-folder',
    files: [
        { basename: 'officer.mp4', path: 'C:/case-folder/officer.mp4', extension: 'mp4', mode: 'bwc', size_bytes: 1024 },
    ],
};

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
            pickFolder: vi.fn(() => Promise.resolve('C:/case-folder')),
        };
        global.fetch = vi.fn((url, opts) => {
            if (url === 'http://127.0.0.1:8888/api/project/open' && opts?.method === 'POST') {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(SAMPLE_MANIFEST),
                });
            }
            return Promise.reject(new Error('unexpected url: ' + url));
        });
    });

    afterEach(() => {
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the empty state on mount', () => {
        render(<EditorApp />);
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('opens a folder, calls /api/project/open, and renders the project view', async () => {
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText('officer.mp4')).toBeDefined();
        });
        expect(window.electronAPI.pickFolder).toHaveBeenCalledTimes(1);
        expect(global.fetch).toHaveBeenCalledWith(
            'http://127.0.0.1:8888/api/project/open',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ path: 'C:/case-folder' }),
            }),
        );
    });

    it('does nothing if the user cancels the folder dialog', async () => {
        window.electronAPI.pickFolder = vi.fn(() => Promise.resolve(null));
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        // Wait a tick to confirm no fetch fired
        await new Promise((r) => setTimeout(r, 10));
        expect(global.fetch).not.toHaveBeenCalled();
        // Still on empty state
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
    });

    it('returns to empty state when the project is closed', async () => {
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText('officer.mp4')).toBeDefined();
        });
        fireEvent.click(screen.getByRole('button', { name: /close/i }));
        expect(screen.getByRole('button', { name: /open folder/i })).toBeDefined();
        expect(screen.queryByText('officer.mp4')).toBeNull();
    });

    it('renders an inline error if /api/project/open fails', async () => {
        global.fetch = vi.fn(() =>
            Promise.resolve({
                ok: false,
                status: 404,
                json: () => Promise.resolve({ error: 'folder not found' }),
            }),
        );
        render(<EditorApp />);
        fireEvent.click(screen.getByRole('button', { name: /open folder/i }));
        await waitFor(() => {
            expect(screen.getByText(/folder not found/i)).toBeDefined();
        });
    });
});
