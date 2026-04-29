import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import EditorApp from './EditorApp.jsx';
import { _resetCachedBaseForTests } from './api.js';

describe('EditorApp', () => {
    beforeEach(() => {
        _resetCachedBaseForTests();
        // Stub electronAPI before each test
        global.window.electronAPI = {
            getEngineUrl: () => Promise.resolve('http://127.0.0.1:8888'),
        };
        // Stub fetch
        global.fetch = vi.fn((url) => {
            if (url === 'http://127.0.0.1:8888/api/version') {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ version: '2026.04.29a' }),
                });
            }
            return Promise.reject(new Error('unexpected url: ' + url));
        });
    });

    afterEach(() => {
        delete global.window.electronAPI;
        global.fetch = undefined;
    });

    it('renders the app title', () => {
        render(<EditorApp />);
        expect(screen.getByText('BWC Clipper')).toBeDefined();
    });

    it('fetches and displays the engine version', async () => {
        render(<EditorApp />);
        await waitFor(() => {
            expect(screen.getByText(/2026\.04\.29a/)).toBeDefined();
        });
    });
});
