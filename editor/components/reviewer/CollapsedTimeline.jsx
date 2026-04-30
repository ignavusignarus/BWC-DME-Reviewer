import React from 'react';

export default function CollapsedTimeline({ cells, currentTime, onSeek, onSilenceClick, expandedSilenceIndex, searchMatches }) {
    return (
        <div data-testid="timeline-collapsed" style={{ display: 'flex', height: 28, width: '100%', background: '#161b22', borderRadius: 3, overflow: 'hidden', position: 'relative' }}>
            {cells.map((c) => {
                const widthStyle = `${c.widthPctCollapsed}%`;
                if (c.kind === 'silence') {
                    return (
                        <div
                            key={c.key}
                            data-testid="silence-cell"
                            data-dur={`${Math.round(c.endSec - c.startSec)}s silence`}
                            onClick={(e) => { e.stopPropagation(); onSilenceClick(c.silenceIndex); }}
                            style={{
                                width: widthStyle,
                                flexShrink: 0,
                                background: 'repeating-linear-gradient(45deg, #21262d 0, #21262d 3px, #161b22 3px, #161b22 6px)',
                                cursor: 'pointer',
                            }}
                            title={`${Math.round(c.endSec - c.startSec)}s silence`}
                        />
                    );
                }
                const inThisCell = currentTime >= c.startSec && currentTime <= c.endSec;
                const matchInCell = searchMatches.some(m => m.start >= c.startSec && m.start <= c.endSec);
                return (
                    <div
                        key={c.key}
                        data-testid="seg-cell"
                        onClick={(e) => {
                            const rect = e.currentTarget.getBoundingClientRect();
                            const fraction = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                            onSeek(c.startSec + fraction * (c.endSec - c.startSec));
                        }}
                        style={{
                            width: widthStyle,
                            flexShrink: 0,
                            background: inThisCell ? '#58d6d6' : '#2ea3a3',
                            cursor: 'pointer',
                            position: 'relative',
                        }}
                    >
                        {inThisCell && (
                            <div style={{
                                position: 'absolute', top: -2, bottom: -2, width: 2,
                                background: '#f0883e',
                                left: `${(currentTime - c.startSec) / Math.max(0.001, c.endSec - c.startSec) * 100}%`,
                            }} />
                        )}
                        {matchInCell && (
                            <div style={{
                                position: 'absolute', top: 2, left: '50%', transform: 'translateX(-50%)',
                                width: 5, height: 5, borderRadius: '50%', background: '#f6c343',
                            }} />
                        )}
                    </div>
                );
            })}
        </div>
    );
}
