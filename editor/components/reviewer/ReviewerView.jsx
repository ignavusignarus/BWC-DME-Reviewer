import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { apiGet } from '../../api.js';
import { ReviewerContext } from './ReviewerContext.js';

// Placeholders — replaced by real components in subsequent tasks
function TopBarPlaceholder({ onBack, source }) {
    return (
        <div data-testid="topbar" style={{ padding: '8px 14px', background: '#161b22', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', gap: 14 }}>
            <button onClick={onBack} style={{ background: 'transparent', color: '#8b949e', border: '1px solid #30363d', borderRadius: 3, padding: '3px 9px' }}>← Project</button>
            <span style={{ fontFamily: 'ui-monospace, monospace', color: '#6e7681', fontSize: '0.78rem' }}>{source.path}</span>
        </div>
    );
}
function MediaPanePlaceholder() { return <div data-testid="mediapane" style={{ flex: 1, background: '#010409' }} />; }
function TranscriptPanelPlaceholder({ transcript }) {
    return (
        <div data-testid="transcriptpanel" style={{ background: '#0d1117', borderLeft: '1px solid #21262d', overflowY: 'auto', flex: 1, padding: '8px 0' }}>
            {transcript.segments.map(s => (
                <div key={s.id} style={{ padding: '7px 12px', color: '#c9d1d9', fontSize: '0.83rem' }}>{s.text}</div>
            ))}
        </div>
    );
}
function TimelinePlaceholder() { return <div data-testid="timeline" style={{ height: 60, background: '#0d1117', borderTop: '1px solid #21262d' }} />; }

export default function ReviewerView({ folder, source, onBack, manifest }) {
    const [transcript, setTranscript] = useState(null);
    const [speechSegments, setSpeechSegments] = useState(null);
    const [error, setError] = useState(null);
    const audioRef = useRef(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [playing, setPlaying] = useState(false);

    useEffect(() => {
        const params = new URLSearchParams({ folder, source: source.path });
        apiGet(`/api/source/transcript?${params.toString()}`)
            .then((doc) => {
                setTranscript(doc.transcript);
                setSpeechSegments(doc.speech_segments);
            })
            .catch(() => setError('Failed to load transcript'));
    }, [folder, source.path]);

    const seekTo = useCallback((seconds) => {
        if (!audioRef.current) return;
        audioRef.current.currentTime = Math.max(0, Math.min(seconds, audioRef.current.duration || 0));
    }, []);
    const play = useCallback(() => audioRef.current?.play(), []);
    const pause = useCallback(() => audioRef.current?.pause(), []);

    const ctx = useMemo(() => ({
        audioRef,
        currentTime, duration, playing,
        seekTo, play, pause,
        folder, source,
    }), [currentTime, duration, playing, seekTo, play, pause, folder, source]);

    if (error) return <div style={{ padding: 24, color: '#f87171' }}>{error}</div>;
    if (!transcript) return <div style={{ padding: 24, color: '#8b949e' }}>Loading transcript…</div>;

    return (
        <ReviewerContext.Provider value={ctx}>
            <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <TopBarPlaceholder onBack={onBack} source={source} />
                <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 360px', minHeight: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                        <MediaPanePlaceholder />
                        <TimelinePlaceholder />
                    </div>
                    <TranscriptPanelPlaceholder transcript={transcript} />
                </div>
                <audio
                    ref={audioRef}
                    src={`/api/source/audio?${new URLSearchParams({ folder, source: source.path }).toString()}`}
                    onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                    onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    style={{ display: 'none' }}
                />
            </div>
        </ReviewerContext.Provider>
    );
}
