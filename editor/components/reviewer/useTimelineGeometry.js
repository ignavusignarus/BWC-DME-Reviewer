import { useMemo } from 'react';

// Collapsed-mode budget: total share of the timeline width allocated to all
// silence cells combined. Speech cells get the remaining (1 - this) and split
// it proportionally to their durations. This guarantees the timeline always
// fits its container, regardless of how many silence intervals exist.
const SILENCE_BUDGET_FRACTION = 0.25;
// Minimum width per silence cell so very short or very many silences stay
// clickable. A silence cell's pct is clamped to at least this many percent.
const SILENCE_MIN_PCT = 0.5;
// When a silence cell is "expanded" (user clicked to peek inside) it grows
// to this share of the timeline. Picked so the expanded cell is reliably
// wider than its peers even when there are only a handful of silences.
const SILENCE_EXPANDED_PCT = 20;

/**
 * Build the interleaved cell list for a timeline.
 *
 * Returns an array of cells where each cell has:
 *   - kind: 'speech' | 'silence'
 *   - startSec / endSec: real-time bounds
 *   - widthPctCollapsed: percent of timeline width in collapsed mode (sum = 100)
 *   - widthPctUncompressed: percent of timeline width in uncompressed mode (= duration share)
 *   - silenceIndex: silence only — 0-based index among silence cells (for expand toggle)
 *   - key: stable React key
 *
 * Both modes use percentage widths so total always fits in the container.
 */
export function computeCells({ speechSegments, durationSeconds, expandedSilenceIndex }) {
    if (!durationSeconds || durationSeconds <= 0) return [];

    // First pass: build raw cells with timing only.
    const raw = [];
    let cursor = 0;
    let silenceCount = 0;
    const pushSilence = (start, end) => {
        if (end <= start) return;
        raw.push({
            kind: 'silence',
            startSec: start,
            endSec: end,
            key: `s-${start}-${end}`,
            silenceIndex: silenceCount,
        });
        silenceCount += 1;
    };
    const pushSpeech = (seg) => {
        raw.push({
            kind: 'speech',
            startSec: seg.start,
            endSec: seg.end,
            key: `p-${seg.start}-${seg.end}`,
        });
    };
    for (const seg of speechSegments) {
        if (seg.start > cursor) pushSilence(cursor, seg.start);
        pushSpeech(seg);
        cursor = seg.end;
    }
    if (cursor < durationSeconds) pushSilence(cursor, durationSeconds);

    // Second pass: compute collapsed-mode percentages.
    // Silence: each gets an equal slice of the silence budget (clamped to min).
    // If one silence is "expanded", it gets SILENCE_EXPANDED_PCT and the rest
    // share the remaining budget.
    // Speech: split remaining width proportional to duration.
    const speechTotalDur = raw
        .filter(c => c.kind === 'speech')
        .reduce((s, c) => s + (c.endSec - c.startSec), 0) || 1;

    let silenceBudget = SILENCE_BUDGET_FRACTION * 100;
    let regularSilenceCount = silenceCount;
    if (expandedSilenceIndex !== null && expandedSilenceIndex < silenceCount) {
        silenceBudget = Math.max(0, silenceBudget - SILENCE_EXPANDED_PCT);
        regularSilenceCount = Math.max(0, silenceCount - 1);
    }
    const perSilencePct = regularSilenceCount > 0
        ? Math.max(SILENCE_MIN_PCT, silenceBudget / regularSilenceCount)
        : 0;

    // Recompute actual silence total (min-clamp may push us over budget) so
    // speech share is reduced accordingly.
    const actualSilenceTotal =
        (regularSilenceCount * perSilencePct) +
        (expandedSilenceIndex !== null ? SILENCE_EXPANDED_PCT : 0);
    const speechBudget = Math.max(0, 100 - actualSilenceTotal);

    return raw.map((c) => {
        const dur = c.endSec - c.startSec;
        const widthPctUncompressed = (dur / durationSeconds) * 100;
        let widthPctCollapsed;
        if (c.kind === 'silence') {
            widthPctCollapsed = c.silenceIndex === expandedSilenceIndex
                ? SILENCE_EXPANDED_PCT
                : perSilencePct;
        } else {
            widthPctCollapsed = (dur / speechTotalDur) * speechBudget;
        }
        return { ...c, widthPctCollapsed, widthPctUncompressed };
    });
}

export function useTimelineGeometry(args) {
    return useMemo(
        () => computeCells(args),
        [args.speechSegments, args.durationSeconds, args.expandedSilenceIndex]
    );
}
