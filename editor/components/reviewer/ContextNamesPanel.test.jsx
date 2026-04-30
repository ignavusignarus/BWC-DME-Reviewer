import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ContextNamesPanel from './ContextNamesPanel.jsx';

beforeEach(() => {
    globalThis.fetch = vi.fn();
});

describe('ContextNamesPanel', () => {
    it('Apply button POSTs context, then retranscribe, in order', async () => {
        fetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: true }) });
        const onStarted = vi.fn();
        render(<ContextNamesPanel folder="/x" sourcePath="/x/y.mp3" onRetranscribeStarted={onStarted} disabled={false} />);
        const namesArea = screen.getByLabelText(/names/i);
        fireEvent.change(namesArea, { target: { value: 'Patel' } });
        fireEvent.click(screen.getByRole('button', { name: /apply/i }));
        await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
        // Order: context first, then retranscribe
        expect(fetch.mock.calls[0][0]).toBe('/api/source/context');
        expect(fetch.mock.calls[1][0]).toBe('/api/source/retranscribe');
        expect(onStarted).toHaveBeenCalled();
    });

    it('disables button while disabled prop is true', () => {
        render(<ContextNamesPanel folder="/x" sourcePath="/x/y.mp3" onRetranscribeStarted={() => {}} disabled />);
        expect(screen.getByRole('button', { name: /apply/i }).disabled).toBe(true);
    });
});
