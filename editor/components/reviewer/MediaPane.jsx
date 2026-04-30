import React from 'react';
import { useReviewer } from './ReviewerContext.js';
import Transport from './Transport.jsx';
import Waveform from './Waveform.jsx';

export default function MediaPane({ onTimeUpdate, onLoadedMetadata, onPlay, onPause, searchQuery, onSearchQueryChange, matchCount, onSearchKeyDown }) {
    const { source, folder, audioRef, engineBase } = useReviewer();
    const isVideo = source.mode === 'bwc';
    const params = new URLSearchParams({ folder, source: source.path }).toString();
    const audioUrl = `${engineBase}/api/source/audio?${params}`;
    const videoUrl = `${engineBase}/api/source/video?${params}`;

    return (
        <div data-testid="mediapane" style={{ flex: 1, background: '#010409', borderRight: '1px solid #21262d', display: 'flex', flexDirection: 'column', padding: 14, minHeight: 0 }}>
            {isVideo ? (
                <video
                    data-testid="video-element"
                    ref={audioRef}
                    src={videoUrl}
                    onTimeUpdate={onTimeUpdate}
                    onLoadedMetadata={onLoadedMetadata}
                    onPlay={onPlay}
                    onPause={onPause}
                    style={{ width: '100%', maxHeight: 360, background: '#000' }}
                    controls={false}
                />
            ) : (
                <>
                    <Waveform url={audioUrl} />
                    <audio
                        ref={audioRef}
                        src={audioUrl}
                        onTimeUpdate={onTimeUpdate}
                        onLoadedMetadata={onLoadedMetadata}
                        onPlay={onPlay}
                        onPause={onPause}
                        style={{ display: 'none' }}
                    />
                </>
            )}
            <Transport />
            <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
                <input
                    type="text"
                    placeholder="Search transcript…"
                    value={searchQuery || ''}
                    onChange={(e) => onSearchQueryChange?.(e.target.value)}
                    onKeyDown={onSearchKeyDown}
                    aria-label="search transcript"
                    style={{ flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 3, color: '#c9d1d9', padding: '5px 9px', fontSize: '0.8rem', fontFamily: 'inherit' }}
                />
                {searchQuery && (
                    <span style={{ color: '#6e7681', fontSize: '0.72rem', fontFamily: 'ui-monospace, monospace' }}>
                        {matchCount} match{matchCount !== 1 ? 'es' : ''}
                    </span>
                )}
            </div>
        </div>
    );
}
