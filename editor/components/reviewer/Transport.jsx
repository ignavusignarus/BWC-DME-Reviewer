import React from 'react';
import { useReviewer } from './ReviewerContext.js';

function fmt(seconds) {
    if (!isFinite(seconds)) return '00:00';
    const total = Math.max(0, Math.floor(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
        return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function Transport() {
    const { play, pause, seekTo, playing, currentTime, duration } = useReviewer();
    const skip = (delta) => seekTo(Math.max(0, Math.min((currentTime ?? 0) + delta, duration ?? 0)));

    return (
        <div role="toolbar" style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
            <button aria-label="Skip back 5 seconds" onClick={() => skip(-5)}
                style={{ background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 3, padding: '4px 8px', cursor: 'pointer' }}>
                ◀◀
            </button>
            {playing
                ? <button aria-label="Pause" onClick={pause}
                    style={{ background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 3, padding: '4px 12px', cursor: 'pointer' }}>⏸</button>
                : <button aria-label="Play" onClick={play}
                    style={{ background: '#2ea3a3', color: '#010409', border: '1px solid #2ea3a3', borderRadius: 3, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>▶</button>}
            <button aria-label="Skip forward 5 seconds" onClick={() => skip(5)}
                style={{ background: '#21262d', color: '#c9d1d9', border: '1px solid #30363d', borderRadius: 3, padding: '4px 8px', cursor: 'pointer' }}>
                ▶▶
            </button>
            <span style={{ marginLeft: 8, fontFamily: 'ui-monospace, monospace', color: '#8b949e', fontSize: '0.78rem' }}>
                {fmt(currentTime)} / {fmt(duration)}
            </span>
        </div>
    );
}
