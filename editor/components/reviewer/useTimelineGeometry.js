import { useMemo } from 'react';

const SILENCE_PX_DEFAULT = 24;
const SILENCE_PX_EXPANDED = 80;
const SPEECH_FLEX_PER_SECOND = 1.0;

/**
 * Build the interleaved cell list for a timeline.
 *
 * Returns an array of cells where each cell has:
 *   - kind: 'speech' | 'silence'
 *   - startSec / endSec: real-time bounds
 *   - flexBasis: speech only — proportional to duration (collapsed mode)
 *   - widthPx: silence only — fixed 24px or 80px when expanded (collapsed mode)
 *   - widthPct: both kinds — percent of total duration (uncompressed mode)
 *   - silenceIndex: silence only — 0-based index among silence cells (for expand toggle)
 *   - key: stable React key
 */
export function computeCells({ speechSegments, durationSeconds, mode, expandedSilenceIndex }) {
    const cells = [];
    let cursor = 0;
    let silenceCount = 0;

    const pushSilence = (start, end) => {
        if (end <= start) return;
        const isExpanded = silenceCount === expandedSilenceIndex;
        const widthPx = isExpanded ? SILENCE_PX_EXPANDED : SILENCE_PX_DEFAULT;
        const widthPct = ((end - start) / durationSeconds) * 100;
        cells.push({
            kind: 'silence',
            startSec: start,
            endSec: end,
            key: `s-${start}-${end}`,
            widthPx,
            widthPct,
            silenceIndex: silenceCount,
        });
        silenceCount += 1;
    };

    const pushSpeech = (seg) => {
        const flexBasis = (seg.end - seg.start) * SPEECH_FLEX_PER_SECOND;
        const widthPct = ((seg.end - seg.start) / durationSeconds) * 100;
        cells.push({
            kind: 'speech',
            startSec: seg.start,
            endSec: seg.end,
            key: `p-${seg.start}-${seg.end}`,
            flexBasis,
            widthPct,
        });
    };

    for (const seg of speechSegments) {
        if (seg.start > cursor) pushSilence(cursor, seg.start);
        pushSpeech(seg);
        cursor = seg.end;
    }
    if (cursor < durationSeconds) pushSilence(cursor, durationSeconds);

    return cells;
}

export function useTimelineGeometry(args) {
    return useMemo(
        () => computeCells(args),
        [args.speechSegments, args.durationSeconds, args.mode, args.expandedSilenceIndex]
    );
}
