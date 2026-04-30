import React, { useEffect, useState } from 'react';
import { useReviewer } from './ReviewerContext.js';
import { useTimelineGeometry } from './useTimelineGeometry.js';
import CollapsedTimeline from './CollapsedTimeline.jsx';
import UncompressedTimeline from './UncompressedTimeline.jsx';

function fmt(s) {
    if (!isFinite(s)) return '00:00';
    const m = Math.floor(Math.max(0, s) / 60);
    const sec = Math.floor(Math.max(0, s) % 60);
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

export default function Timeline({ speechSegments, duration, searchMatches }) {
    const { currentTime, seekTo } = useReviewer();
    const [mode, setMode] = useState('collapsed');
    const [expandedSilenceIndex, setExpandedSilenceIndex] = useState(null);

    const cells = useTimelineGeometry({
        speechSegments,
        durationSeconds: duration,
        mode,
        expandedSilenceIndex,
    });

    useEffect(() => {
        const onKey = (e) => {
            const tag = (e.target && e.target.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;
            if (e.key === 'Escape' && expandedSilenceIndex !== null) {
                setExpandedSilenceIndex(null);
                e.preventDefault();
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [expandedSilenceIndex]);

    const handleSilence = (silenceIndex) => {
        setExpandedSilenceIndex((prev) => (prev === silenceIndex ? null : silenceIndex));
    };

    return (
        <div style={{ background: '#0d1117', borderTop: '1px solid #21262d', padding: '8px 14px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.72rem', color: '#6e7681' }}>
                <span style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Timeline · {mode === 'collapsed' ? 'collapsed silence' : 'uncompressed'}
                </span>
                <button
                    onClick={() => setMode((m) => (m === 'collapsed' ? 'uncompressed' : 'collapsed'))}
                    aria-label={mode === 'collapsed' ? 'switch to uncompressed' : 'switch to collapsed'}
                    style={{ background: 'transparent', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '2px 8px', fontSize: '0.7rem', cursor: 'pointer' }}>
                    ⇄ {mode === 'collapsed' ? 'uncompressed' : 'collapsed'}
                </button>
                <span style={{ marginLeft: 'auto', fontFamily: 'ui-monospace, monospace', color: '#c9d1d9', fontSize: '0.78rem' }}>
                    {fmt(currentTime)} / {fmt(duration)}
                </span>
            </div>
            {mode === 'collapsed' ? (
                <CollapsedTimeline
                    cells={cells}
                    currentTime={currentTime}
                    onSeek={seekTo}
                    onSilenceClick={handleSilence}
                    expandedSilenceIndex={expandedSilenceIndex}
                    searchMatches={searchMatches}
                />
            ) : (
                <UncompressedTimeline
                    cells={cells}
                    durationSeconds={duration}
                    currentTime={currentTime}
                    onSeek={seekTo}
                    searchMatches={searchMatches}
                />
            )}
        </div>
    );
}
