import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { apiGet } from '../../api.js';
import { ReviewerContext } from './ReviewerContext.js';
import TopBar from './TopBar.jsx';
import MediaPane from './MediaPane.jsx';
import TranscriptPanel from './TranscriptPanel.jsx';
import ContextNamesPanel from './ContextNamesPanel.jsx';
import { usePolling } from '../../usePolling.js';
function TimelinePlaceholder() { return <div data-testid="timeline" style={{ height: 60, background: '#0d1117', borderTop: '1px solid #21262d' }} />; }

export default function ReviewerView({ folder, source, onBack, manifest }) {
    const [searchQuery, setSearchQuery] = useState('');
    const [transcript, setTranscript] = useState(null);
    const [speechSegments, setSpeechSegments] = useState(null);
    const [error, setError] = useState(null);
    const audioRef = useRef(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [retranscribeStatus, setRetranscribeStatus] = useState(null);
    const [staleTranscript, setStaleTranscript] = useState(false);

    useEffect(() => {
        let cancelled = false;
        // Reset state immediately so the previous source's data doesn't flash
        // through during the fetch. Important for cross-source navigation.
        setTranscript(null);
        setSpeechSegments(null);
        setError(null);
        setCurrentTime(0);
        setDuration(0);
        setPlaying(false);

        const params = new URLSearchParams({ folder, source: source.path });
        apiGet(`/api/source/transcript?${params.toString()}`)
            .then((doc) => {
                if (cancelled) return;
                setTranscript(doc.transcript);
                setSpeechSegments(doc.speech_segments);
            })
            .catch(() => {
                if (cancelled) return;
                setError('Failed to load transcript');
            });

        return () => { cancelled = true; };
    }, [folder, source.path]);

    const fetchStatus = useCallback(async () => {
        const params = new URLSearchParams({ folder, source: source.path });
        const resp = await apiGet(`/api/source/state?${params.toString()}`);
        return resp.status === 'idle' ? null : resp.status;
    }, [folder, source.path]);

    const polling = usePolling(fetchStatus, retranscribeStatus !== null);

    useEffect(() => {
        if (polling.status) setRetranscribeStatus(polling.status);
        if (polling.status === 'completed') {
            const params = new URLSearchParams({ folder, source: source.path });
            apiGet(`/api/source/transcript?${params.toString()}`).then((doc) => {
                setTranscript(doc.transcript);
                setSpeechSegments(doc.speech_segments);
                setStaleTranscript(false);
                setRetranscribeStatus(null);
            });
        }
    }, [polling.status, folder, source.path]);

    const onRetranscribeStarted = () => {
        setStaleTranscript(true);
        setRetranscribeStatus('queued');
    };

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

    const onTimeUpdate = (e) => setCurrentTime(e.currentTarget.currentTime);
    const onLoadedMetadata = (e) => setDuration(e.currentTarget.duration);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);

    if (error) return <div style={{ padding: 24, color: '#f87171' }}>{error}</div>;
    if (!transcript) return <div style={{ padding: 24, color: '#8b949e' }}>Loading transcript…</div>;

    return (
        <ReviewerContext.Provider value={ctx}>
            <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <TopBar
                    manifest={manifest}
                    source={source}
                    onBack={onBack}
                    onSelectSource={(f) => { /* TODO(task-21): cross-source nav */ }}
                    retranscribeStatus={retranscribeStatus}
                />
                <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 360px', minHeight: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                        <MediaPane
                            onTimeUpdate={onTimeUpdate}
                            onLoadedMetadata={onLoadedMetadata}
                            onPlay={onPlay}
                            onPause={onPause}
                        />
                        <TimelinePlaceholder />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, borderLeft: '1px solid #21262d' }}>
                        {staleTranscript && retranscribeStatus === 'failed' && (
                            <div style={{ background: '#161b22', borderBottom: '1px solid #f87171', color: '#f87171', padding: '6px 12px', fontSize: '0.78rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span>Re-transcribe failed — showing previous results</span>
                                <button
                                    onClick={() => { setStaleTranscript(false); setRetranscribeStatus(null); }}
                                    style={{ background: 'transparent', color: '#f87171', border: '1px solid #f87171', borderRadius: 3, padding: '2px 8px', fontSize: '0.7rem', cursor: 'pointer' }}>
                                    Dismiss
                                </button>
                            </div>
                        )}
                        {staleTranscript && retranscribeStatus !== 'failed' && (
                            <div style={{ background: '#161b22', borderBottom: '1px solid #d29922', color: '#d29922', padding: '6px 12px', fontSize: '0.78rem' }}>
                                Re-transcribing — showing previous results
                            </div>
                        )}
                        <TranscriptPanel transcript={transcript} searchQuery={searchQuery} />
                        <ContextNamesPanel
                            folder={folder}
                            sourcePath={source.path}
                            onRetranscribeStarted={onRetranscribeStarted}
                            disabled={retranscribeStatus !== null}
                        />
                    </div>
                </div>
            </div>
        </ReviewerContext.Provider>
    );
}
