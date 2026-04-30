import { useEffect, useRef, useState } from 'react';

const POLL_INTERVAL_MS = 1000;
const TERMINAL = new Set(['completed', 'failed', 'idle']);

/**
 * Polls fetchStatus() every 1 s while enabled. Returns the latest status.
 * Stops automatically when status enters {completed, failed, idle}.
 */
export function usePolling(fetchStatus, enabled) {
    const [status, setStatus] = useState(null);
    const handle = useRef(null);

    useEffect(() => {
        if (!enabled) return undefined;
        const tick = async () => {
            try {
                const next = await fetchStatus();
                setStatus(next);
                if (TERMINAL.has(next)) {
                    clearInterval(handle.current);
                    handle.current = null;
                }
            } catch (err) {
                console.warn('[usePolling] fetch failed:', err);
            }
        };
        handle.current = setInterval(tick, POLL_INTERVAL_MS);
        return () => {
            if (handle.current) {
                clearInterval(handle.current);
                handle.current = null;
            }
        };
    }, [fetchStatus, enabled]);

    return { status };
}
