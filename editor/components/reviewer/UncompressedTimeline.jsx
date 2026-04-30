import React from 'react';

function pickTickInterval(duration) {
    if (duration <= 60) return 5;
    if (duration <= 600) return 60;
    if (duration <= 3600) return 600;
    return 1800;
}

function fmtTick(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return s === 0 ? `${m}:00` : `${m}:${String(s).padStart(2, '0')}`;
}

export default function UncompressedTimeline({ cells, durationSeconds, currentTime, onSeek, searchMatches }) {
    const tickInterval = pickTickInterval(durationSeconds);
    const ticks = [];
    for (let t = 0; t <= durationSeconds; t += tickInterval) {
        ticks.push(t);
    }

    const onTrackClick = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        onSeek(fraction * durationSeconds);
    };

    return (
        <div data-testid="timeline-uncompressed" style={{ background: '#161b22', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ height: 14, background: '#0d1117', position: 'relative', borderBottom: '1px solid #21262d', color: '#6e7681', fontSize: '0.62rem' }}>
                {ticks.map(t => (
                    <span key={t} style={{ position: 'absolute', left: `${(t / durationSeconds) * 100}%`, top: 1, transform: 'translateX(-50%)' }}>
                        {fmtTick(t)}
                    </span>
                ))}
            </div>
            <div onClick={onTrackClick} style={{ height: 24, position: 'relative', cursor: 'pointer' }}>
                {cells.filter(c => c.kind === 'speech').map(c => (
                    <div key={c.key} style={{
                        position: 'absolute',
                        left: `${(c.startSec / durationSeconds) * 100}%`,
                        width: `${c.widthPctUncompressed}%`,
                        top: 4,
                        height: 16,
                        background: '#2ea3a3',
                        borderRadius: 2,
                    }} />
                ))}
                {searchMatches.map((m, i) => (
                    <div key={i} style={{
                        position: 'absolute',
                        bottom: 0,
                        left: `${(m.start / durationSeconds) * 100}%`,
                        width: 5,
                        height: 5,
                        borderRadius: '50%',
                        background: '#f6c343',
                        transform: 'translateX(-50%)',
                    }} />
                ))}
                <div style={{
                    position: 'absolute',
                    top: 0,
                    bottom: 0,
                    width: 2,
                    background: '#f0883e',
                    left: `${(currentTime / durationSeconds) * 100}%`,
                }} />
            </div>
        </div>
    );
}
