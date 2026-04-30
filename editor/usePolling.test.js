import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePolling } from './usePolling.js';

beforeEach(() => {
    vi.useFakeTimers();
    globalThis.jest = { advanceTimersByTime: vi.advanceTimersByTime };
});

describe('usePolling', () => {
    it('does not poll when disabled', () => {
        const fetchStatus = vi.fn(() => Promise.resolve('queued'));
        renderHook(() => usePolling(fetchStatus, false));
        vi.advanceTimersByTime(5000);
        expect(fetchStatus).not.toHaveBeenCalled();
    });

    it('polls every 1 s while enabled and updates status', async () => {
        const fetchStatus = vi.fn()
            .mockResolvedValueOnce('queued')
            .mockResolvedValueOnce('running:transcribe')
            .mockResolvedValueOnce('completed');
        const { result } = renderHook(() => usePolling(fetchStatus, true));
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(1000); });
        expect(result.current.status).toBe('completed');
    });

    it('stops polling once status reaches a terminal value', async () => {
        const fetchStatus = vi.fn()
            .mockResolvedValueOnce('completed');
        renderHook(() => usePolling(fetchStatus, true));
        await act(async () => { vi.advanceTimersByTime(1000); });
        await act(async () => { vi.advanceTimersByTime(2000); });
        expect(fetchStatus).toHaveBeenCalledTimes(1);
    });
});
