# Milestone 6 — Reviewer UI Design

Status: Draft (post-brainstorm, pre-plan)
Parent spec: [2026-04-29-bwc-clipper-design.md](./2026-04-29-bwc-clipper-design.md) (§6 in particular)

---

## 1. Overview

M6 is the first milestone that puts an end-user-facing review experience in front of the actual person reviewing media. M0–M5 produced a working transcription pipeline whose only output is a JSON file on disk; M6 turns that JSON into a navigable surface a litigator can actually use to scrub a 60-minute DME exam or a 91-minute BWC video and find the moments that matter.

The defining UX problem M6 solves matches the parent spec's framing: long stretches of silence, sparse moments of relevance, and a transcript that should serve as a fast navigation aid (not a deliverable on the clip itself). The collapsed-silence timeline is the key feature that distinguishes this app from a generic media player with captions.

## 2. Scope

### In scope (M6 V1 = full §6 minus M8-dependent surfaces)

The user opted for the full §6 surface area in this milestone, with the explicit exception of pieces that depend on the clip data model that ships in M8.

- Engine endpoints to stream the original audio (DME) or video (BWC) over loopback HTTP with full Range-request support.
- Engine endpoint to read the assembled transcript + speech segments in one fetch.
- Engine endpoints to write per-source context (`names`, `locations`) and trigger a re-run of stages 5+6.
- Engine endpoint to read/write a per-project "last opened source" persistence file.
- Reviewer view (replaces the current single-page project view as a second view in `EditorApp`):
  - Top bar with `← Project` button, folder breadcrumb, source picker (filtered to sources that have a completed `transcript.json`), and a re-transcribe progress pill.
  - Media pane: `<video>` for BWC mode, rendered waveform + `<audio>` for DME mode, transport row, search box.
  - Transcript panel (right column, fixed 360 px) with active-utterance highlight, auto-scroll-to-follow with manual-scroll suspension, low-confidence amber underline, click-to-seek.
  - Context-names panel (collapsible `<details>` at the bottom of the transcript panel).
  - Timeline pane with two views — collapsed-silence (default) and uncompressed — switchable by `⇄` toggle. Search match markers on both.
- Hotkey handling for the playback subset only: Space, J/K/L, ←/→, Shift+←/→, /, Ctrl+S (no-op until M8), ⇄ (timeline toggle).

### Out of scope (deferred)

- **Clip-authoring hotkeys (I, O, Enter, Esc)** — defer to M8 with the clip data model. Bindings are explicitly unregistered in M6 to avoid silent dead-keys.
- **Clip-list sidebar** — defer to M8.
- **Top-bar Export button** — defer to M8.
- **Top-bar telemetry indicator** — defer; depends on the §9 job system.
- **Diarization-driven speaker colors and labels** — defer to M7. In M6, every utterance renders with a single accent color and a generic "Speaker:" label (or just the timestamp). The transcript schema's `speakers` field is `[]` until M7.
- **Pre-rendered waveform peaks (`peaks.json` cache stage)** — defer. M6 decodes audio in the renderer via `AudioContext.decodeAudioData` and downsamples to ~2,000 peaks. If perf is unacceptable on long sources we revisit.
- **Resizable splitters** — defer. M6 uses a fixed CSS grid (1fr | 360 px).
- **Playhead position persistence across sessions** — defer. M6 persists last-opened-source per project, nothing else.
- **Cancel-in-flight re-transcription** — defer. Re-runs are short (~30 s on a long DME with a 5080); add a Cancel button only if real users complain.

## 3. Architecture overview

M6 introduces no new tier or framework. The existing three-tier shape (Electron spawn → Python engine HTTP → React renderer) carries everything.

```
Electron main      ──spawn──►  Python engine (now multithreaded HTTP)
                                │
                                ├─ /api/source/audio      (Range)
                                ├─ /api/source/video      (Range)
                                ├─ /api/source/transcript (JSON)
                                ├─ /api/source/context    (POST)
                                ├─ /api/source/retranscribe (POST)
                                ├─ /api/project/reviewer-state (GET/POST)
                                └─ existing M0–M5 routes
                                      ▲
                                      │ fetch / Range
                                      │
React renderer ─────────────────── EditorApp router
                                    ├─ EmptyState
                                    ├─ ProjectView         (existing)
                                    └─ ReviewerView        (new)
                                          ├─ TopBar
                                          ├─ MediaPane (Audio | Video + Waveform)
                                          ├─ TranscriptPanel
                                          │    └─ ContextNamesPanel
                                          └─ Timeline (CollapsedTimeline | UncompressedTimeline)
```

Key invariants kept from prior milestones:

- Engine remains the single source of truth for `.bwcclipper/` access. The renderer never reads from disk via `file://`.
- Pipeline contract is unchanged. `transcript.json` schema is exactly what M5 ships; M6 reads it as-is.
- No new ML model dependencies in M6. The re-transcribe path re-uses the M5 stage 5+6 implementations untouched.
- Engine spawn-and-stdout-port handshake is unchanged.

## 4. Engine changes

### 4.1 Threading

`serve.py` swaps `HTTPServer` for a small `ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer)` subclass with `daemon_threads = True` and a `handle_error` that logs rather than crashes. This is the proven pattern from Depo Clipper (`serve.py:3636`).

**Why required, not optional:** browser `<audio>` and `<video>` elements maintain open HTTP connections for Range-based streaming. With single-threaded `HTTPServer`, a streaming response blocks every other request — including the polling that drives the re-transcribe progress pill — until the response finishes writing. Multithreading the request handlers is the simplest fix; pipeline work stays serialized in the existing single-worker `ThreadPoolExecutor` so we don't introduce GPU concurrency.

### 4.2 Media streaming endpoints

Two new GET endpoints on `engine/server.py`:

- `GET /api/source/audio?folder=<path>&source=<path>` — streams the original audio file at the resolved source path. For the DME mode (`<audio>` element).
- `GET /api/source/video?folder=<path>&source=<path>` — streams the original video file. For the BWC mode (`<video>` element).

Both endpoints share a single `_serve_media(file_path, fallback_mime)` helper. The audio endpoint passes `fallback_mime="audio/wav"`; the video endpoint passes `"video/mp4"`. Each route additionally validates that the resolved source's mode matches the endpoint (audio endpoint rejects video sources with `415 Unsupported Media Type`, and vice versa) — defense in depth even though the renderer is the only legitimate caller. The helper:

1. Validates the resolved path is inside the project folder (defense in depth — even though the engine is loopback-only, never trust query-string paths).
2. Uses `mimetypes.guess_type` for the content type, falling back to the endpoint's `fallback_mime`.
3. Reads `Range: bytes=START-END` if present:
   - Parses with regex `r"bytes=(\d+)-(\d*)"`.
   - Sends `206 Partial Content` with `Content-Range: bytes START-END/SIZE`, `Content-Length: LENGTH`, `Accept-Ranges: bytes`, `Connection: close`, plus the CORS headers below.
   - Streams the requested byte range in 64 KiB chunks via `f.seek(start)` + `f.read(min(chunk, remaining))`.
4. With no Range header, sends `200` with the full file, same connection-close behavior.
5. Catches `BrokenPipeError`, `ConnectionResetError`, `ConnectionAbortedError`, and Windows `OSError` errnos `10053`/`10054` silently — they fire constantly during normal seek and the renderer is unaffected.

CORS headers exposed: `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Range`, `Access-Control-Expose-Headers: Content-Range, Accept-Ranges, Content-Length`. The expose-headers entry is critical — without it, the renderer can't read `Content-Length` from the response and the `<video>` element can't compute a duration.

`Connection: close` is intentional: without it, long-lived video connections eat the browser's per-origin connection limit (typically 6) and starve the API endpoints.

The original audio variant is what gets served — not `enhanced/track0.wav`. The reasoning: clips export from the original (per parent spec §8), so the reviewer should hear what will end up in trial. `enhanced/track0.wav` exists only as a transcription input, not a listening surface.

### 4.3 Transcript fetch endpoint

`GET /api/source/transcript?folder=<path>&source=<path>` returns one combined JSON document so the reviewer mounts in a single fetch:

```json
{
  "transcript": { ... contents of transcript.json ... },
  "speech_segments": [ { "start": 1.5, "end": 4.2 }, ... ]
}
```

The `speech_segments` array is `tracks[0]` from `speech-segments.json` — multi-track support is not in M6 V1 (matches the rest of the pipeline; current sources have one audio track).

### 4.4 Context-names endpoint

`POST /api/source/context` with body:

```json
{
  "folder": "C:/cases/williams-2024",
  "source": "C:/cases/williams-2024/dme/williams-ent-exam.mp3",
  "names": ["Dr. Patel", "Heather Williams"],
  "locations": ["CVS Crenshaw", "Saint Mary's clinic"]
}
```

The handler validates types (lists of strings), creates the cache directory if needed, and writes `<cache_dir>/context.json`. Returns `200 {"ok": true}`. Does **not** trigger re-transcription on its own — that's a separate call so the renderer can persist drafts without immediately re-running the pipeline.

`engine/pipeline/transcribe.py:177-198` already reads `context.json` and threads it into faster-whisper as `initial_prompt`. M6 adds only the write path.

### 4.5 Re-transcribe endpoint

`POST /api/source/retranscribe` with body `{folder, source}`. Calls a new `runner.rerun_from_stage("transcribe", folder, source)`, then returns the new status (`{"status": "queued"}` or whatever `runner.get_status` returns).

The new `rerun_from_stage(stage_name, folder, source)` method on `PipelineRunner`:

1. Looks up the stage index in `_PIPELINE_STAGES`.
2. Loads `<cache_dir>/pipeline-state.json`.
3. For the named stage and every subsequent stage: marks `status` as `pending`, clears `started_at`/`completed_at`/`outputs`/`error`.
4. Saves `pipeline-state.json`.
5. Calls `submit_pipeline(folder, source)` — the existing skip-when-completed logic in `_run_pipeline` will skip stages 1–4 (still `completed`) and run 5–6.

Idempotent if the source is already queued — `submit_pipeline` is idempotent on a queued source per existing M3 behavior.

**Forward note for M7:** `rerun_from_stage` walks `_PIPELINE_STAGES` from the named index forward, so when M7 inserts diarization and wearer-detect stages **after** `align`, the same call (`rerun_from_stage("transcribe", ...)`) will correctly invalidate them too. The list ordering is the contract — M7 must place new stages after `align`.

### 4.6 Reviewer-state endpoint

A small per-project "last opened source" persistence:

- `GET /api/project/reviewer-state?folder=<path>` — reads `<folder>/.bwcclipper/reviewer-state.json`. Returns `{"last_source": null}` if the file doesn't exist.
- `POST /api/project/reviewer-state` with body `{folder, last_source}`. Writes the file.

The implementation lives in a new module `engine/reviewer_state.py`. Round-trip-tested. Not used for clip drafts or playhead position — those are separate concerns deferred beyond M6.

## 5. Editor (React) changes

### 5.1 View routing

`EditorApp.jsx` becomes a three-state router on `view: "empty" | "project" | "reviewer"`. No router library — a switch in the top-level component is enough. Closing back from reviewer to project view sets `view = "project"` and preserves the manifest (no re-fetch).

Source selection from the project view branches:

- If the source has `transcript.json` (`status === "completed"`): set `view = "reviewer"`, `selectedReviewSource = file`.
- Otherwise: existing M2-M5 behavior — submit to runner, poll status. The existing `FileListItem` already shows stage progress.

### 5.2 New component tree

Under `editor/components/reviewer/`:

- `ReviewerView.jsx` — root of the reviewer tree. Fetches `/api/source/transcript` once on mount, holds transcript + speech segments in state, owns the `<audio>`/`<video>` ref, drives `timeupdate` → active-segment derivation. Provides a `ReviewerContext` so children can call `seekTo(seconds)`, `play()`, `pause()`, etc., without prop drilling.
- `TopBar.jsx` — `← Project` button, folder breadcrumb, source picker, retranscribe progress pill. The picker is a `<select>` populated from the manifest, filtered to entries whose status is `completed`. Re-transcribe pill renders only when the active source's status starts with `running:` and includes the stage name.
- `MediaPane.jsx` — branches on the source's mode (`audio` or `video`, from the manifest). For video: renders `<video src="/api/source/video?…" />` plus the transport row underneath. For audio: renders the `<Waveform>` component, then `<audio src="/api/source/audio?…" />` (visually hidden — controls live on the transport row), then the transport row, then the search input.
- `Waveform.jsx` (DME only) — fetches the audio bytes via the same audio URL, decodes via `AudioContext.decodeAudioData`, downsamples to ~2,000 peaks (`Math.ceil(channelLength / peakCount)` samples per peak, taking max-abs), renders to an HTML5 `<canvas>`. Re-renders only on resize — peaks are computed once per source. Decoding a 60-min audio is a few seconds; we show a "Loading waveform…" placeholder during it.
- `Transport.jsx` — buttons for Play/Pause, ◀◀ (Shift+←: -1 s), ▶▶ (Shift+→: +1 s), -5 s (←), +5 s (→), and a time readout (`mm:ss / mm:ss`). All call into `ReviewerContext`.
- `TranscriptPanel.jsx` — virtual-scroll-friendly rendering of the segment list (in V1, plain DOM rendering — 1,225 nodes is fine; we virtualize only if a future source forces it). Active utterance gets a teal left-border + tinted background. Auto-scroll to keep active in view; suspends on detected `wheel`/`touchstart`/`scroll` user input; resumes on user click on a segment or a hotkey-driven seek. Hosts the `ContextNamesPanel` at the bottom.
- `ContextNamesPanel.jsx` — `<details>` element. Two textareas (one per line input), "Apply & re-transcribe" button. On click: `POST /api/source/context`, then `POST /api/source/retranscribe`, then enable the polling loop on the active source. Disables itself while a re-run is in flight.
- `Timeline.jsx` — owns the mode toggle. Internally branches between `<CollapsedTimeline>` and `<UncompressedTimeline>`. Both share the `useTimelineGeometry` hook (§6 below). Owns click-to-seek dispatch and silence-bar expand state.
- `SearchHighlight.jsx` — utility. Takes a string and the active query, returns React fragments with `<mark>` around case-insensitive substring matches. Used by the transcript panel.

### 5.3 State shape

Inside `ReviewerView`:

```js
{
  loading: boolean,
  error: string | null,
  transcript: TranscriptJson | null,
  speechSegments: [{start, end}, ...] | null,
  audio: { ref, currentTime, duration, playing },
  search: { query, matches: [{segmentId, segmentStart, segmentEnd}] },
  timeline: { mode: "collapsed" | "uncompressed", expandedSilenceIndex: number | null },
  retranscribeStatus: null | "queued" | "running:transcribe" | "running:align" | "completed" | "failed",
  // The renderer normalizes the engine's "idle" status to null (re-run not in flight).
  staleTranscript: boolean,    // true while a re-run is in flight
}
```

Search matches recompute whenever `transcript` or `query` changes. The active segment is derived (not stored) — a `useMemo` over `transcript.segments` + `currentTime` returns the current segment id.

### 5.4 Hotkeys

A single `useEffect` on `ReviewerView` registers a window-level `keydown` handler that:

1. If the event target is `<input>` or `<textarea>`, return early (search box and context textareas absorb keys).
2. Otherwise dispatch:
   - `Space` → toggle play/pause
   - `J` → reverse playback (sets `playbackRate = -1`; pause if already reverse)
   - `K` → pause
   - `L` → forward playback (`playbackRate = 1`)
   - `←` → seek -5 s
   - `→` → seek +5 s
   - `Shift+←` → seek -1 s
   - `Shift+→` → seek +1 s
   - `/` → focus the search input
   - `Ctrl+S` → no-op (reserved for M8 clip save). Prevents browser's "save page" dialog.
   - `Esc` → if a silence is currently expanded in the timeline, collapse it; otherwise no-op (standard browser behavior preserved). M8 will extend Esc to also clear in/out marks.
   - `⇄` is a button only; not a hotkey.

`I`, `O`, `Enter` are deliberately **not** bound in M6. M8 will register them on the clip editor's mount. Leaving them unbound (rather than no-op'd) means standard browser behavior remains — Enter does nothing surprising in the reviewer surface.

### 5.5 Polling

The existing `EditorApp` polling pattern for `/api/source/state` is reused but moved into a `usePolling(folder, source, enabled)` hook so both the project view and the reviewer view's re-transcribe pill use the same code. Polls every 1 s (existing constant) while `enabled === true`; stops when status is `completed` or `failed`.

When a re-transcribe completes:

1. Polling stops.
2. `ReviewerView` refetches `/api/source/transcript`.
3. State updates: `transcript`, `speechSegments`, `staleTranscript = false`, `retranscribeStatus = null`.
4. `<audio>` / `<video>` `currentTime` is preserved (re-seated on the existing element; the audio file didn't change).
5. Search matches recompute against the new transcript.

## 6. Timeline rendering

### 6.1 Geometry hook

A single `useTimelineGeometry(speechSegments, durationSeconds, mode)` hook returns a sorted array of cells:

```ts
type Cell = {
  kind: "speech" | "silence",
  startSec: number,
  endSec: number,
  // collapsed mode:
  flexBasis?: number,    // for speech cells
  widthPx?: number,      // for silence cells (24 default, 80 expanded)
  // uncompressed mode:
  widthPct?: number,     // (endSec - startSec) / durationSeconds * 100
  key: string,
}
```

Both views render from the same cell list — the layout strategy differs per `kind` per `mode`. This means click-to-seek and search-marker placement share one code path across views.

Silence cells are derived from gaps between speech cells: walk the sorted speech list, emit a silence cell for any gap > 0 between consecutive speech segments. Edge silences (before the first speech segment, after the last) are also emitted if the gap is non-trivial.

### 6.2 Click-to-seek mapping

- **Inside a speech cell:** linear interpolation. `clickX / cellWidth → fraction`, then `seekTo(cell.startSec + fraction * (cell.endSec - cell.startSec))`. Identical math in both views.
- **Inside a collapsed silence cell (not expanded):** seek to `cell.startSec` (i.e., "skip to where this silence began" — useful as a reverse-skip; the more common forward case is users clicking the next speech cell directly).
- **Inside an expanded silence cell:** linear interpolation across the silence's real time range. The expand interaction exists exactly so users can seek into a long silence if they need to.
- **In uncompressed mode silences (just track gaps):** the gap is part of the dark track; clicks on the dark track use the cell at that pixel position via `useTimelineGeometry`'s reverse lookup.

### 6.3 Silence-bar interaction (collapsed mode)

- Hover: tooltip `M:SS silence` (formatted from `cell.endSec - cell.startSec`).
- Click: toggle `expandedSilenceIndex`. Only one silence is expanded at a time; clicking another collapses the previous.
- `Esc` key: collapses any expanded silence (only when no input is focused).
- Top-bar "⤢ expand all silences" button: temporarily renders the timeline as if all silences had `widthPct` (uncompressed widths) while keeping the speech-cell flex geometry. Effectively a hybrid view. Toggles back on second click.

### 6.4 Active-segment + playhead

Driven by the `<audio>`/`<video>` `timeupdate` event. Active-segment derivation searches the **raw `speechSegments` array** (not the geometry cells), since the geometry cells include silences and the active surface is always a speech cell:

1. Binary-search `speechSegments` for the segment containing `currentTime`. If none (we're in a gap), the "active" cell is the previous speech segment (i.e., the segment with the largest `end <= currentTime`). The same array supports both branches with one search.
2. Active cell gets a `.active` class (brighter teal + light outline).
3. Playhead is a 2 px orange overlay positioned absolutely inside the active cell:
   - In a speech cell: `left = ${(currentTime - cell.startSec) / cellDuration * 100}%`.
   - In a silence (collapsed mode): pinned to the right edge of the previous speech cell. Visual cue that we're between segments.
   - In a silence (uncompressed mode): real X position over the dark track gap.

### 6.5 Search markers

Computed from `search.matches`. For each match's containing transcript segment, find which timeline cell contains the segment's mid-time:

- Collapsed view: small gold dot (5 px, `border-radius: 50%`) at the top of the matching cell, multiple dots stack horizontally if more than one match falls in the same cell.
- Uncompressed view: gold dot below the cell ruler, aligned to the segment's start time.

Markers are clickable — click jumps to the match's segment start.

### 6.6 Toggle and performance

`⇄` button instantly swaps `mode`. The geometry hook recomputes; React reconciles cells in place; no animation. Audio playback is unaffected.

A 60-min DME with 1,225 segments → ~2,000 timeline cells. Tested cheap in flexbox. We virtualize only if a 4-hour source forces it; not in V1.

## 7. Search

- **Scope:** `segment.text` only. Word-level entries are ignored — segments are the navigation unit.
- **Match semantics:** case-insensitive substring (`segment.text.toLowerCase().includes(query.toLowerCase())`).
- **Debounce:** 100 ms on input change.
- **UI surfaces:**
  - Transcript panel: matching substring spans wrapped in `<mark>` (`SearchHighlight` utility).
  - Timeline (both views): gold dots at matching segments.
- **Active-match navigation:** Enter inside the search box jumps to next match; Shift+Enter jumps backward. Implementation: track an `activeMatchIndex` in search state, scroll the matching utterance into view, seek to the segment start.
- **Empty query:** clears all marks and dots; no scroll change.

## 8. Re-transcribe lifecycle

```
idle ── click "Apply & re-transcribe" ──►
  POST /api/source/context (writes context.json)
  POST /api/source/retranscribe (marks transcribe+align pending; submits)
  staleTranscript = true; retranscribeStatus = "queued"
  ── poll /api/source/state every 1 s ──►
       "running:transcribe" → "running:align" → "completed"
                                              → "failed"
  on completed:  refetch /api/source/transcript; replace in-memory data;
                 staleTranscript = false; retranscribeStatus = null;
                 preserve playhead; recompute search matches.
  on failed:     show red banner with the error; stay on stale data;
                 user can retry.
```

During a re-run:

- The transcript panel keeps showing the previous data (it was loaded into React state at mount).
- A stale banner appears at the top of the transcript pane: "Re-transcribing — showing previous results".
- Click-to-seek still works against the old timestamps.
- The re-transcribe progress pill in the top bar shows the current stage.
- Cross-source navigation: polling continues for the rerunning source. The pill in the top bar identifies the source by name when the user is viewing a different source. When the rerun completes, if the user is back on that source, refetch & swap; if not, just clear the pill — the next time they open that source they'll see fresh data.

Idempotency: clicking Apply twice in quick succession is a no-op on the second click (the source is already queued; the runner already has the job).

## 9. State persistence

Per-project file at `<folder>/.bwcclipper/reviewer-state.json`:

```json
{ "last_source": "C:/cases/williams-2024/dme/williams-ent-exam.mp3" }
```

- Written when the user navigates into a source's reviewer view.
- Read when the user opens a project. If `last_source` is present and that source still has a completed transcript, the editor jumps directly to the reviewer view; otherwise it shows the project view as today.
- Not written on close — closing back to the project view doesn't change the "last" anchor.

Playhead position, search query, and timeline mode are intentionally **not** persisted in M6.

## 10. Testing strategy

### 10.1 Engine unit tests (mock-only, fast)

- `tests/test_server_media.py` — Range header parsing (full file, partial, open-ended `bytes=START-`, malformed → 416), 206 response shape, headers (`Content-Range`/`Accept-Ranges`/`Connection: close`), CORS exposure correct. Uses `BytesIO` rather than spinning the server up.
- `tests/test_server_routes_m6.py` — `/api/source/audio` and `/api/source/video` route to `_serve_media` with correct file path resolved from manifest validation; missing file → 404; mode mismatch (audio request on a video source) → 415.
- `tests/test_server_context.py` — `POST /api/source/context` writes JSON correctly, validates `names`/`locations` are list-of-string, creates parent dirs.
- `tests/test_server_retranscribe.py` — `POST /api/source/retranscribe` invokes `runner.rerun_from_stage` with right args; idempotent on repeated calls.
- `tests/test_runner_rerun.py` — `rerun_from_stage` correctly marks `transcribe` + `align` as `pending`, leaves stages 1–4 alone, calls `submit_pipeline`. Existing pipeline-runner tests cover the actual re-execution.
- `tests/test_reviewer_state.py` — `reviewer-state.json` round-trip; missing file returns sensible defaults.

### 10.2 Engine integration tests (real I/O, `@pytest.mark.integration`)

- `tests/integration/test_reviewer_endpoints.py`:
  - Spin engine on a port, fetch a Range slice from a fixture audio with `urllib.request`, verify bytes match the on-disk file at that offset. Proof that streaming actually works (the unit test only verifies header math).
  - **Range stress test:** Range fetch into the middle of `Samples/BWC/tja00453_…mp4` (3.95 GB). Catches any 32-bit offset math mistakes and verifies `Connection: close` actually closes the socket so subsequent API calls don't block.
  - End-to-end short-fixture round-trip of context-edit → retranscribe → poll-until-complete → fetch transcript → verify the new `initial_prompt` was honored (a name in the context appears in the new transcript that didn't before). Slow but irreplaceable.

### 10.3 Editor tests (Vitest + RTL)

Per component, in `editor/components/reviewer/*.test.jsx`:

- `ReviewerView.test.jsx` — mounts, fetches, exposes context; cleans up on unmount; cross-source switching swaps state cleanly.
- `TopBar.test.jsx` — source picker filters to completed sources; selection swaps active source; back button transitions to project view.
- `MediaPane.test.jsx` — branches audio/video by mode; transport buttons call audio API; ±5 s skip respects `[0, duration]` bounds.
- `Waveform.test.jsx` — given a known PCM buffer (mock `AudioContext.decodeAudioData`), downsamples to expected peak count.
- `TranscriptPanel.test.jsx` — active utterance gets `.active`; auto-scroll triggers when active changes; manual scroll suspends auto-scroll; click on utterance calls seek.
- `Timeline.test.jsx` — geometry hook returns expected cells for fixture inputs; click-to-seek interpolates correctly inside cells; silence-bar expand/collapse toggles; toggle button switches mode; Esc collapses expanded silence.
- `ContextNamesPanel.test.jsx` — Apply button POSTs context first, then retranscribe, in order; renders progress pill while running; reverts to idle on completion.
- `Search.test.jsx` — debounced 100 ms; case-insensitive substring; matches highlight in both panel and timeline; Enter / Shift+Enter cycles matches; clear restores full list.
- `Hotkeys.test.jsx` — Space, J/K/L, ←/→, Shift+←/→, /, Ctrl+S behave as documented; letter keys absorbed inside textarea/input; I/O/Enter explicitly do nothing.

### 10.4 Manual burn-in checklist

Documented in HANDOFF.md as part of the milestone close:

1. Open the Williams ENT DME (60 min), reach reviewer view, hear audio, see transcript, see timeline.
2. Click a transcript utterance — audio jumps to that timestamp.
3. Search for a known phrase — see highlights in transcript, gold markers on timeline; Enter/Shift+Enter cycles matches.
4. Edit context names ("Patel", "Williams"), click Apply, watch retranscribe complete in ~30 s, see new transcript with names spelled correctly.
5. Open `Samples/BWC/`, select `pia00458_…mp4` (~91 min), verify the `<video>` element loads, scrub the timeline, confirm seek lands within ~50 ms of the click target.
6. Toggle ⇄ between collapsed and uncompressed views — both render correctly, click-to-seek consistent.

### 10.5 Note on existing flake

`tests/test_server_source.py::test_unknown_post_path_returns_404` will continue to flake on Windows per the existing memory note. M6 introduces no new flake risk in this area — Range responses use `Connection: close` precisely to avoid the read-side of similar Windows TCP behavior.

## 11. File-by-file checklist

For the writing-plans skill to expand into ordered work units:

**Engine:**
- `serve.py` — replace `HTTPServer` with `ThreadedHTTPServer` (~10 lines).
- `engine/server.py` — extend GET routes (`/api/source/audio`, `/api/source/video`, `/api/source/transcript`, `/api/project/reviewer-state`); extend POST routes (`/api/source/context`, `/api/source/retranscribe`, `/api/project/reviewer-state`); add `_serve_media` helper; expand CORS headers; handle Range; absorb expected disconnects.
- `engine/pipeline/runner.py` — add `rerun_from_stage` method.
- `engine/reviewer_state.py` — new module, ~30 lines.

**Editor:**
- `editor/EditorApp.jsx` — view-routing state.
- `editor/components/reviewer/ReviewerView.jsx` (new)
- `editor/components/reviewer/TopBar.jsx` (new)
- `editor/components/reviewer/MediaPane.jsx` (new)
- `editor/components/reviewer/Waveform.jsx` (new)
- `editor/components/reviewer/Transport.jsx` (new)
- `editor/components/reviewer/TranscriptPanel.jsx` (new)
- `editor/components/reviewer/ContextNamesPanel.jsx` (new)
- `editor/components/reviewer/Timeline.jsx` (new), with `CollapsedTimeline.jsx`, `UncompressedTimeline.jsx`, `useTimelineGeometry.js`
- `editor/components/reviewer/SearchHighlight.jsx` (new utility)
- `editor/usePolling.js` (new shared hook; refactor existing EditorApp polling)
- `editor/api.js` — add `apiPostJson` if not already present; otherwise unchanged.

**Tests:** see §10.

## 12. Decisions log

Each decision was made during the brainstorm session that produced this spec, with a recommendation and a confirmation:

1. **Scope of M6:** full §6 from parent spec, minus M8-dependent pieces (clip list, I/O/Enter/Esc, export, telemetry). Confirmed.
2. **Media delivery:** engine HTTP endpoint with HTTP Range support, ported from Depo Clipper's proven pattern. Rejected: Electron custom protocol (splits cache-path logic across JS+Python), `file://` (requires loosened Electron security).
3. **Audio variant served in DME:** the original media file. Rejected: `enhanced/track0.wav` (drifts from what's in trial), toggle (added scope without clear V1 value).
4. **Re-transcribe granularity:** mark stages 5+6 as pending and re-submit; runner's existing skip-when-completed handles the rest. Rejected: full re-run from stage 1 (wasteful); generic `invalidate_from_stage` (premature generalization).
5. **Re-transcribe UX:** stale banner over previous transcript (per spec §6.5); cross-source navigation continues re-run in background. Rejected: spinner-only (loses navigation during re-run); cancel-on-navigate (throws away in-flight work).
6. **Speaker colors in M6:** single accent color since `transcript.json.speakers` is `[]` until M7.
7. **Silence bar visual:** fixed 24 px striped grey, hover tooltip with duration, click expands inline to ~80 px, Esc collapses.
8. **Search:** segment-text only, case-insensitive substring, 100 ms debounce, gold markers on timeline.
9. **State persistence:** last opened source per project; nothing else (no playhead, no search query, no timeline mode).
10. **Layout:** fixed CSS grid with 360 px transcript pane; no resizable splitters in V1.
11. **BWC fixtures:** `Samples/BWC/` provides real test material. `pia00458_…mp4` (~91 min) is the first end-to-end BWC integration target. `tja00453_…mp4` (3.95 GB) is the Range-correctness stress check.

---

End of spec.
