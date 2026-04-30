import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { apiGet, getBaseUrl } from '../../api.js';
import { ReviewerContext } from './ReviewerContext.js';
import TopBar from './TopBar.jsx';
import MediaPane from './MediaPane.jsx';
import TranscriptPanel from './TranscriptPanel.jsx';
import Timeline from './Timeline.jsx';

export default function ReviewerView({ folder, source, onBack, manifest, onSelectSource }) {
    const [searchInput, setSearchInput] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [activeMatchIndex, setActiveMatchIndex] = useState(-1);
    const [transcript, setTranscript] = useState(null);
    const [speechSegments, setSpeechSegments] = useState(null);
    const [error, setError] = useState(null);
    const [engineBase, setEngineBase] = useState(null);
    const audioRef = useRef(null);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [playing, setPlaying] = useState(false);

    useEffect(() => {
        let cancelled = false;
        getBaseUrl().then((base) => { if (!cancelled) setEngineBase(base); });
        return () => { cancelled = true; };
    }, []);

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
                // Defensive renumbering: faster-whisper's Segment.id is 0 for
                // every segment when vad_filter=True, and older cached
                // transcripts may carry the same defect. The DOM lookup that
                // auto-scrolls the active segment relies on unique IDs.
                const segs = doc.transcript.segments.map((s, i) => ({ ...s, id: i }));
                setTranscript({ ...doc.transcript, segments: segs });
                setSpeechSegments(doc.speech_segments);
            })
            .catch(() => {
                if (cancelled) return;
                setError('Failed to load transcript');
            });

        return () => { cancelled = true; };
    }, [folder, source.path]);

    useEffect(() => {
        const t = setTimeout(() => setSearchQuery(searchInput), 100);
        return () => clearTimeout(t);
    }, [searchInput]);

    const searchMatches = useMemo(() => {
        if (!searchQuery || !transcript) return [];
        const q = searchQuery.toLowerCase();
        return transcript.segments
            .filter(s => s.text.toLowerCase().includes(q))
            .map(s => ({ segmentId: s.id, start: s.start, end: s.end }));
    }, [searchQuery, transcript]);

    useEffect(() => {
        setActiveMatchIndex(-1);
    }, [searchQuery]);

    const seekTo = useCallback((seconds) => {
        if (!audioRef.current) return;
        audioRef.current.currentTime = Math.max(0, Math.min(seconds, audioRef.current.duration || 0));
    }, []);
    const play = useCallback(() => audioRef.current?.play(), []);
    const pause = useCallback(() => audioRef.current?.pause(), []);

    const onSearchKeyDown = useCallback((e) => {
        if (e.key !== 'Enter' || !searchMatches.length) return;
        e.preventDefault();
        const next = e.shiftKey
            ? (activeMatchIndex - 1 + searchMatches.length) % searchMatches.length
            : (activeMatchIndex + 1) % searchMatches.length;
        setActiveMatchIndex(next);
        seekTo(searchMatches[next].start);
    }, [searchMatches, activeMatchIndex, seekTo]);

    useEffect(() => {
        const onKey = (e) => {
            const tag = (e.target && e.target.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA') return;
            switch (e.key) {
                case ' ':
                    e.preventDefault();
                    if (audioRef.current?.paused) play(); else pause();
                    break;
                case 'k':
                case 'K':
                    pause();
                    break;
                case 'j':
                case 'J':
                    if (audioRef.current) audioRef.current.playbackRate = -1;
                    play();
                    break;
                case 'l':
                case 'L':
                    if (audioRef.current) audioRef.current.playbackRate = 1;
                    play();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    seekTo((audioRef.current?.currentTime || 0) + (e.shiftKey ? -1 : -5));
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    seekTo((audioRef.current?.currentTime || 0) + (e.shiftKey ? 1 : 5));
                    break;
                case '/':
                    e.preventDefault();
                    document.querySelector('input[placeholder*="Search" i]')?.focus();
                    break;
                case 's':
                case 'S':
                    if (e.ctrlKey || e.metaKey) e.preventDefault();
                    break;
                case 'Escape':
                    if (document.activeElement?.tagName === 'INPUT') document.activeElement.blur();
                    break;
                default:
                    return;
            }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [play, pause, seekTo]);

    const ctx = useMemo(() => ({
        audioRef,
        currentTime, duration, playing,
        seekTo, play, pause,
        folder, source,
        engineBase: engineBase || '',
    }), [currentTime, duration, playing, seekTo, play, pause, folder, source, engineBase]);

    const onTimeUpdate = (e) => setCurrentTime(e.currentTarget.currentTime);
    const onLoadedMetadata = (e) => setDuration(e.currentTarget.duration);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);

    if (error) return <div style={{ padding: 24, color: '#f87171' }}>{error}</div>;
    if (!transcript || engineBase === null) return <div style={{ padding: 24, color: '#8b949e' }}>Loading transcript…</div>;

    return (
        <ReviewerContext.Provider value={ctx}>
            <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
                <TopBar
                    manifest={manifest}
                    source={source}
                    onBack={onBack}
                    onSelectSource={onSelectSource}
                />
                <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', minHeight: 0 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
                        <MediaPane
                            onTimeUpdate={onTimeUpdate}
                            onLoadedMetadata={onLoadedMetadata}
                            onPlay={onPlay}
                            onPause={onPause}
                            searchQuery={searchInput}
                            onSearchQueryChange={setSearchInput}
                            matchCount={searchMatches.length}
                            onSearchKeyDown={onSearchKeyDown}
                        />
                        <Timeline
                            speechSegments={speechSegments || []}
                            duration={transcript?.source?.duration_seconds || 0}
                            searchMatches={searchMatches}
                        />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, borderLeft: '1px solid #21262d' }}>
                        <TranscriptPanel transcript={transcript} searchQuery={searchQuery} />
                    </div>
                </div>
            </div>
        </ReviewerContext.Provider>
    );
}
