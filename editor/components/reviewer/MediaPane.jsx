import React from 'react';
import { useReviewer } from './ReviewerContext.js';
import Transport from './Transport.jsx';
import Waveform from './Waveform.jsx';

export default function MediaPane({ onTimeUpdate, onLoadedMetadata, onPlay, onPause }) {
    const { source, folder, audioRef } = useReviewer();
    const isVideo = source.mode === 'video';
    const params = new URLSearchParams({ folder, source: source.path }).toString();
    const audioUrl = `/api/source/audio?${params}`;
    const videoUrl = `/api/source/video?${params}`;

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
        </div>
    );
}
