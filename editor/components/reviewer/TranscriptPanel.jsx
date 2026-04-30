import React, { useEffect, useMemo, useRef } from 'react';
import { useReviewer } from './ReviewerContext.js';
import SearchHighlight from './SearchHighlight.jsx';

const LOW_CONF_WORD_SCORE = 0.6;

function fmtTs(seconds) {
    const total = Math.max(0, Math.floor(seconds || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
        return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function activeIndex(segments, currentTime) {
    // Last segment with start <= currentTime. -1 if none yet.
    let lo = 0, hi = segments.length - 1, ans = -1;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (segments[mid].start <= currentTime) { ans = mid; lo = mid + 1; }
        else hi = mid - 1;
    }
    return ans;
}

export default function TranscriptPanel({ transcript, searchQuery }) {
    const { currentTime, seekTo } = useReviewer();
    const segments = transcript.segments;
    const active = useMemo(() => activeIndex(segments, currentTime), [segments, currentTime]);
    const listRef = useRef(null);
    const userScrolled = useRef(false);

    useEffect(() => {
        const el = listRef.current;
        if (!el) return;
        const onUserScroll = () => { userScrolled.current = true; };
        el.addEventListener('wheel', onUserScroll, { passive: true });
        el.addEventListener('touchstart', onUserScroll, { passive: true });
        return () => {
            el.removeEventListener('wheel', onUserScroll);
            el.removeEventListener('touchstart', onUserScroll);
        };
    }, []);

    useEffect(() => {
        if (userScrolled.current) return;
        if (active < 0) return;
        const el = listRef.current?.querySelector(`[data-segment-id="${segments[active].id}"]`);
        if (el && typeof el.scrollIntoView === 'function') {
            el.scrollIntoView({ block: 'center', behavior: 'auto' });
        }
    }, [active, segments]);

    const onClickSegment = (s) => {
        userScrolled.current = false;  // resume auto-follow
        seekTo(s.start);
    };

    return (
        <div ref={listRef} role="region" aria-label="transcript" style={{ background: '#0d1117', borderLeft: '1px solid #21262d', overflowY: 'auto', flex: 1 }}>
            {segments.map((s, idx) => {
                const isActive = idx === active;
                return (
                    <div
                        key={s.id}
                        data-segment-id={s.id}
                        data-active={isActive}
                        onClick={() => onClickSegment(s)}
                        style={{
                            padding: '7px 12px', cursor: 'pointer',
                            borderLeft: `3px solid ${isActive ? '#2ea3a3' : 'transparent'}`,
                            background: isActive ? 'rgba(46, 163, 163, 0.13)' : undefined,
                            fontSize: '0.83rem', lineHeight: 1.45, color: '#c9d1d9',
                        }}
                    >
                        <span style={{ fontFamily: 'ui-monospace, monospace', color: '#8b949e', fontSize: '0.72rem', marginRight: 8 }}>
                            {fmtTs(s.start)}
                        </span>
                        <span style={{ color: '#2ea3a3', fontWeight: 600, marginRight: 4 }}>Speaker:</span>
                        <SegmentText segment={s} query={searchQuery} />
                    </div>
                );
            })}
        </div>
    );
}

function SegmentText({ segment, query }) {
    if (segment.words && segment.words.length > 0) {
        return (
            <>
                {segment.words.map((w, i) => {
                    const lowConf = (w.score ?? 1) < LOW_CONF_WORD_SCORE;
                    return (
                        <React.Fragment key={i}>
                            {i > 0 ? ' ' : ''}
                            <span data-low-conf={lowConf} style={lowConf ? { textDecoration: 'underline', textDecorationColor: '#d29922', textDecorationThickness: 2 } : undefined}>
                                <SearchHighlight text={w.word} query={query} />
                            </span>
                        </React.Fragment>
                    );
                })}
            </>
        );
    }
    return <SearchHighlight text={segment.text} query={query} />;
}
