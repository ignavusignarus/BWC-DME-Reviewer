# Body-Worn Camera Transcription Pipeline — Implementation Brief

## 1. Project Goal

Build a Python-based transcription pipeline that produces accurate, evidentiary-quality transcripts from body-worn camera (BWC) footage for use in civil litigation. Raw Whisper is unsuitable for this audio out of the box; the pipeline must mitigate three specific failure modes:

1. **Hallucination during non-speech** — Whisper invents text during silence, wind, radio static, and ambient noise (e.g., "Thanks for watching," looped phrases).
2. **Dropouts on quiet speakers** — non-wearer speech is often soft, distant, or muffled; Whisper either skips it or transcribes it incoherently.
3. **Background-noise interference** — traffic, sirens, HVAC, crowd noise degrade WER substantially.

The output must include word-level timestamps, speaker labels, and per-segment confidence scores so a human reviewer can efficiently verify against the source video.

## 2. Constraints

- **Use context:** plaintiff-side litigation. Transcripts are draft/navigation aids, not standalone evidence. Original audio integrity must be preserved (hash-verified). Final transcripts entering the record are human-verified.
- **Runtime:** Local processing only. No cloud services. Subject audio may be sealed/protected.
- **Hardware target:** Workstation with NVIDIA GPU (RTX 3090 / 4090 class, 16+ GB VRAM). CPU-only fallback acceptable but slow.
- **OS targets:** Windows 10/11 primary (corporate environment), macOS secondary. Linux for development.
- **Packaging:** Eventually a desktop app similar to Depo Clipper architecture — Python backend, optional Electron/React frontend. For now, build the CLI/library core and design clean interfaces for a UI later.
- **Corporate-environment compatibility:** Avoid PyInstaller `--onefile` (CrowdStrike/Carbon Black flag it). Use `--onedir` or a per-user NSIS installer. No UAC prompts.

## 3. Pipeline Architecture

```
INPUT: BWC video file (Axon .mp4, Motorola .mkv, generic .mp4/.mov/.avi)
   │
   ▼
[1] Audio extraction & track separation (ffmpeg)
   │   → one or more 16 kHz mono WAV files per audio track
   ▼
[2] Loudness normalization + dynamic range compression (ffmpeg)
   │   → normalized WAV
   ▼
[3] Speech enhancement (DeepFilterNet 3)
   │   → enhanced WAV
   ▼
[4] Voice Activity Detection (Silero VAD or pyannote VAD)
   │   → list of (start, end) speech segments
   ▼
[5] Transcription (WhisperX / faster-whisper, large-v3)
   │   → segments with text + word-level timestamps + logprobs
   ▼
[6] Diarization (pyannote 3.x)
   │   → speaker labels per segment
   ▼
[7] Speaker assignment heuristic (wearer detection)
   │   → labeled segments (Officer / Subject 1 / Subject 2 / ...)
   ▼
[8] Output assembly (JSON + WebVTT + plain text + .docx)
   │
OUTPUT: transcript bundle for reviewer UI
```

## 4. Component Specifications

### 4.1 Audio Extraction (`extract.py`)

**Responsibility:** Pull audio from arbitrary BWC video containers, normalize to 16 kHz mono WAV.

**Implementation notes:**
- Use bundled ffmpeg (same approach as Depo Clipper). Static binary in `vendor/ffmpeg/`.
- Probe with `ffprobe` first. Some Axon `.mp4` files have separate audio tracks per officer mic — extract each track to its own WAV (`{basename}_track{N}.wav`) and process them independently. Mixing them down loses speaker isolation.
- Standard parameters: `-ac 1 -ar 16000 -c:a pcm_s16le`.
- Compute and store SHA-256 of original file before any processing. Persist in metadata.

**Interface:**
```python
def extract_audio(video_path: Path, out_dir: Path) -> List[AudioTrack]:
    """Returns list of AudioTrack(path, track_index, duration, source_hash)."""
```

### 4.2 Normalization & Compression (`preprocess.py`)

**Responsibility:** Even out the gulf between the chest-mic'd wearer and distant speakers.

**ffmpeg filter chain (in order):**
1. `loudnorm=I=-16:LRA=11:TP=-1.5` — EBU R128 two-pass loudness normalization.
2. `acompressor=threshold=-24dB:ratio=4:attack=20:release=250:makeup=6` — aggressive compression to lift soft speakers. Tune ratio up to 6:1 if needed for very distant voices.
3. `highpass=f=80, lowpass=f=8000` — modest band-limiting to drop rumble and HF hiss outside speech band.

Order matters: normalize → enhance (next step) → compress. Compressing before enhancement amplifies noise floor.

**Note:** Two-pass `loudnorm` is meaningfully better than single-pass on highly variable BWC audio. Run measurement pass first, then apply with measured values.

### 4.3 Speech Enhancement (`enhance.py`)

**Responsibility:** Suppress wind, traffic, HVAC, crowd noise without speech artifacting.

**Library:** DeepFilterNet 3 (`deepfilternet` on PyPI, ONNX runtime).

**Why DF3 over alternatives:**
- Faster than Resemble Enhance, lower VRAM.
- Less artifacting than VoiceFixer on already-intelligible speech (VoiceFixer over-restores and can shift voice timbre).
- Permissive license (Apache 2.0).

**Fallback:** RNNoise via ffmpeg `arnndn` filter if DF3 unavailable. Lower quality but no extra dependency.

**Interface:**
```python
def enhance(wav_path: Path, out_path: Path, model: str = "DeepFilterNet3") -> Path
```

### 4.4 Voice Activity Detection (`vad.py`)

**Responsibility:** Identify speech regions; suppress hallucination input.

**Default:** Silero VAD (lightweight, fast, good enough). Pyannote VAD as alternative when diarization is already loaded.

**Parameters:**
- `threshold=0.5` (Silero default; lower to 0.4 if missing soft speech)
- `min_speech_duration_ms=250`
- `min_silence_duration_ms=300`
- `speech_pad_ms=200` — pad each segment to avoid clipping word edges

**Output:** list of `(start_seconds, end_seconds)` tuples.

### 4.5 Transcription (`transcribe.py`)

**Library:** WhisperX (`whisperx` on PyPI), backed by faster-whisper (CTranslate2).

**Model:** `large-v3` for production. `large-v3-turbo` only if runtime is critical and audio is relatively clean. Provide a config flag.

**Critical decoder parameters (anti-hallucination):**
```python
asr_options = {
    "condition_on_previous_text": False,    # critical on noisy audio
    "no_speech_threshold": 0.6,             # raise from default 0.45
    "compression_ratio_threshold": 2.4,     # detect looping/repetition
    "logprob_threshold": -1.0,              # flag low-confidence
    "temperature": [0.0, 0.2, 0.4],         # fallback ladder, no higher
    "beam_size": 5,
    "patience": 1.0,
    "suppress_tokens": [-1],
    "without_timestamps": False,
}
```

**Initial prompt:** Accept a user-provided context string. Default template:
> "This is audio from a law enforcement body-worn camera recording an interaction between officers and civilians. Names mentioned may include: [INSERT KNOWN NAMES]. Locations include: [INSERT LOCATIONS]."

Names dramatically improve proper-noun recall. Caller passes them in.

**Word-level alignment:** Use WhisperX forced alignment (wav2vec2-based) post-transcription. Non-negotiable — required for clickable/searchable transcripts.

**Output schema (per segment):**
```python
{
    "id": int,
    "start": float,           # seconds
    "end": float,
    "text": str,
    "words": [{"word": str, "start": float, "end": float, "score": float}],
    "avg_logprob": float,
    "no_speech_prob": float,
    "compression_ratio": float,
    "low_confidence": bool,   # derived from thresholds
}
```

### 4.6 Diarization (`diarize.py`)

**Library:** pyannote.audio 3.x with `pyannote/speaker-diarization-3.1` pipeline.

**Auth:** HuggingFace token required for pyannote model download. Document setup; cache models locally so subsequent runs are offline.

**Parameters:**
- Pass `min_speakers` and `max_speakers` if known (BWC scenes are usually 2–6 speakers).
- Run on the *original* (non-enhanced) audio. Enhancement can smooth out speaker-distinguishing characteristics.

### 4.7 Wearer Detection Heuristic (`speakers.py`)

**Responsibility:** Auto-label one diarization cluster as "Wearer" / "Officer."

**Heuristic:**
- The wearer's voice is consistently the loudest and has the highest proportion of total speech time (chest mic).
- Compute mean RMS amplitude per cluster across all its segments.
- Cluster with highest mean RMS *and* >25% of total speech time → label "Wearer."
- Remaining clusters → "Subject 1," "Subject 2," ... ordered by first appearance.

**Optional enhancement (later):** Voice-print matching against a known sample (e.g., officer deposition audio) using pyannote embeddings. If user provides a labeled sample, match clusters by cosine similarity of mean embedding.

### 4.8 Output Assembly (`output.py`)

Generate three artifacts from the same internal data structure:

1. **`{basename}.transcript.json`** — full structured output (segments, words, speakers, confidence, source hash, processing parameters). Source of truth.
2. **`{basename}.vtt`** — WebVTT with speaker prefixes. Loadable in any HTML5 video player for synchronized playback.
3. **`{basename}.txt`** — plain readable transcript with timestamps and speaker labels (for paste-into-brief use).
4. **`{basename}.docx`** *(optional)* — formatted Word doc with timestamps as a column, suitable for client review.

**JSON schema (top level):**
```json
{
  "schema_version": "1.0",
  "source": {
    "path": "...",
    "sha256": "...",
    "duration_seconds": 1234.5,
    "tracks": [{"index": 0, "channel": "officer_chest"}]
  },
  "processing": {
    "pipeline_version": "0.1.0",
    "whisper_model": "large-v3",
    "vad": "silero",
    "diarization": "pyannote/speaker-diarization-3.1",
    "enhanced": true,
    "timestamp_utc": "2026-04-29T..."
  },
  "speakers": [
    {"id": "SPEAKER_00", "label": "Wearer", "speech_seconds": 412.3},
    {"id": "SPEAKER_01", "label": "Subject 1", "speech_seconds": 198.7}
  ],
  "segments": [ /* see 4.5 */ ]
}
```

## 5. Configuration

YAML config file with sane defaults; CLI flags override:

```yaml
input:
  video_path: ./case_files/incident_001.mp4
  context_names: ["Officer Garcia", "Officer Lee", "Mr. Johnson"]
  context_locations: ["Crenshaw Boulevard"]

processing:
  whisper_model: large-v3
  device: cuda          # cuda | cpu
  compute_type: float16 # float16 | int8_float16 | int8
  vad: silero
  enhance: true
  diarize: true
  min_speakers: null
  max_speakers: 6

output:
  dir: ./output
  formats: [json, vtt, txt, docx]
  flag_low_confidence: true
```

## 6. CLI

```
bodycam-transcribe \
  --input incident_001.mp4 \
  --context-names "Officer Garcia,Mr. Johnson" \
  --output ./output \
  --model large-v3
```

Library entry point:
```python
from bodycam_transcribe import Pipeline
result = Pipeline.from_config("config.yaml").run()
```

## 7. Dependencies

- Python 3.11
- `faster-whisper`, `whisperx`
- `pyannote.audio>=3.1`
- `silero-vad`
- `deepfilternet`
- `torch` with CUDA 12.x build
- `ffmpeg-python` wrapper (binary bundled separately in `vendor/`)
- `pydantic` for config and schemas
- `python-docx` for .docx output
- `webvtt-py` for WebVTT
- `click` for CLI

Pin everything in `requirements.txt` with hashes. Use `uv` or `pip-tools` for resolution.

## 8. Testing & Validation

### 8.1 Unit tests
- Audio extraction: known-input → expected sample rate, channel count, duration.
- VAD: synthetic audio with known silence/speech regions → segment boundaries within 100ms tolerance.
- Output schema: validate generated JSON against pydantic model.

### 8.2 Integration tests
- Fixture set: 5–10 short BWC clips (30–120 seconds each) with manually verified ground-truth transcripts. Cover: officer-only speech, multi-speaker, distant subject, heavy traffic, radio chatter, wind, indoor vs. outdoor.
- Metrics: WER (overall and per-speaker), word-level timestamp drift, hallucination rate (segments matching known hallucination patterns), missed-speech rate.
- Track these across pipeline changes. Regression on any one is a build failure.

### 8.3 Manual review burn-in
Process 3–5 hours of real bodycam audio. Review with the eventual human-reviewer UI in mind — flag failure modes that automated metrics miss (e.g., correctly transcribed but wrong speaker assignment).

## 9. Packaging (Phase 2)

Match Depo Clipper's approach:
- PyInstaller `--onedir` (NOT `--onefile`) to avoid AV/EDR flagging.
- Per-user NSIS installer for Windows. Install to `%LOCALAPPDATA%\BodycamTranscribe`. No admin rights, no UAC.
- Bundle ffmpeg, DeepFilterNet ONNX, Silero ONNX, faster-whisper CT2 model, pyannote pipeline.
- Model files are large (large-v3 ≈ 3 GB; pyannote ≈ 100 MB). Offer a "lite installer" that downloads models on first run versus a "full installer" that bundles them, similar to how some IDEs ship.
- macOS `.app` via `py2app`, signed and notarized.
- Optional Electron + React frontend later, with the CLI/library as the engine — same architectural split as Depo Clipper.

## 10. Known Issues & Risks

| Risk | Mitigation |
|------|-----------|
| Whisper still hallucinates inside long VAD-flagged segments with fluctuating noise | Monitor `compression_ratio` and `avg_logprob`; flag for human review |
| pyannote diarization model license requires HF token & accepting terms | Document one-time setup; cache locally |
| Axon proprietary `.mp4` variants occasionally need specific ffmpeg builds | Test with real Axon Evidence.com exports; bundle a recent ffmpeg with full codec support |
| GPU OOM on long files with large-v3 | Process in chunks aligned to VAD boundaries; expose chunk size as config |
| DeepFilterNet can occasionally over-suppress quiet legitimate speech | Make enhancement toggleable per-run; if WER on soft speakers drops, allow `--no-enhance` |
| Word-level alignment occasionally drifts on overlapping speech | Note drift in confidence; flag overlaps in output |
| Diarization counts swing on short utterances | Use `min_speakers`/`max_speakers` when known; allow manual cluster merging in reviewer UI |

## 11. Stretch Goals

- **Speaker re-identification across files.** Maintain a per-case voice-print database so the same officer is consistently labeled across all evidence in a matter.
- **Reviewer UI.** React app: video player + transcript pane, click-to-seek, low-confidence highlighting, inline correction with revision history. Export corrected transcript back to JSON.
- **Redaction tooling.** Auto-redact (bleep + transcript replacement) for protected names, juveniles, etc., driven by the names list in the config.
- **Synchronized exhibit generation.** Given a corrected transcript and time range, output a clipped video + burned-in subtitles + transcript excerpt as a single bundle ready to drop into a brief. (Natural extension of Depo Clipper.)
- **Quality reports.** Per-file PDF: audio quality metrics, speaker time breakdown, low-confidence segment list, hallucination flags. Useful for declaring transcript reliability for the record.

## 12. Implementation Order

1. **Skeleton & config** — pydantic models, CLI scaffold, output schema. No actual processing yet.
2. **Audio extraction + preprocessing** — ffmpeg pipeline, end-to-end with tests.
3. **VAD + transcription (no enhancement, no diarization)** — get a basic transcript out. Validate against fixtures.
4. **Speech enhancement** — A/B test WER with and without DF3.
5. **Diarization + wearer heuristic** — speaker labels.
6. **Output formats** — JSON, VTT, TXT, DOCX.
7. **Integration test suite + metrics tracking.**
8. **Packaging.**
9. **Reviewer UI** (separate project, consumes JSON).

Each step should produce a runnable, testable artifact. Don't build the whole pipeline before running anything end-to-end.
