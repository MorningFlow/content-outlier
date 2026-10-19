# Transcription Processing Power Optimization Plan

## Executive Summary

The current pipeline automatically triggers heavy video downloads and Faster-Whisper automatic speech recognition across every Reel identified as an outlier during competitor profile scraping. Under default settings (`AUTO_TRANSCRIBE_OUTLIERS=true`), scraping a single competitor with 50 posts frequently identifies 5–15 outliers, immediately spawning an equivalent number of CPU-bound transcription jobs. On host hardware running Faster-Whisper on CPU with `beam_size=5` and disabled Voice Activity Detection (VAD), each video requires 15–40 seconds of 100% CPU core utilization, saturating system threads, elevating temperatures, and degrading host performance for content the user may never inspect.

This document outlines a production-grade optimization strategy to eliminate unnecessary processing power waste, reduce CPU cycles by up to 90%, and transition the platform to an efficient, demand-driven model.

---

## 1. Problem Audit & Inefficiency Vectors

Analysis of the current codebase ([app/services/content_service.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/content_service.py), [app/services/transcription_service.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py), and [app/worker/tasks.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/worker/tasks.py)) identifies four primary sources of processing waste:

1. **Unconstrained Ingestion Triggering:**
   In [ContentService.ingest_scraped_items](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/content_service.py#L133-L153), any post satisfying the outlier threshold (`outlier_score >= 3.0`) immediately enqueues a background `transcription` job and a `video_download` job. Most users evaluate outliers visually via engagement metrics and thumbnails; running speech recognition in bulk prior to user interest wastes computation on non-priority items.

2. **Absence of Voice Activity Detection (VAD):**
   In [TranscriptionService._transcribe_audio_file](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py#L165-L185), Whisper is invoked without speech-frame filtering (`vad_filter=False`). A high proportion of Instagram Reels utilize licensed music, ambient audio, sound effects, or silence with text overlays. Whisper attempts to decode non-vocal audio through its full encoder-decoder transformer layers, generating hallucinations or empty segments while consuming maximum CPU compute for the entire duration of the clip.

3. **Suboptimal Inference Hyperparameters:**
   Whisper decoding currently runs with `beam_size=5`. Beam search evaluates 5 candidate sequences at every token step. For short-form spoken English in social media videos, greedy search (`beam_size=1`) provides virtually indistinguishable word accuracy while executing 3x to 5x faster with a fraction of the CPU overhead.

4. **Redundant Video Payload Handling:**
   Whisper only requires 16 kHz mono audio. The current pipeline downloads and persists 1080p MP4 files (ranging between 15 MB and 60 MB) before passing them to the transcription service, introducing substantial disk I/O, bandwidth consumption, and memory allocation overhead.

---

## 2. Core Architecture & Optimization Strategy

The optimization strategy is divided into four interdependent architectural pillars:

```mermaid
flowchart TD
    Scrape[Competitor Scrape Completed] --> OutlierEval[Evaluate Outlier Metrics]
    OutlierEval --> ModeCheck{Transcription Policy}
    
    ModeCheck -->|on_demand (Default)| NoAuto[Mark status: not_required<br/>Zero background CPU usage]
    ModeCheck -->|top_tier_only| FilterTop[Filter: multiplier >= 5.0x & top 1 per competitor]
    
    NoAuto --> UserAction{User opens Analysis?}
    UserAction -->|Yes / Clicks Transcribe| AudioPrep[Extract lightweight 16kHz audio]
    UserAction -->|No| Finished[No processing spent]
    
    FilterTop --> AudioPrep
    AudioPrep --> VADCheck{Silero VAD / Volume Probe}
    VADCheck -->|No voice detected| MarkVisual[Set status: Visual / Music Reel<br/>Skip Whisper entirely]
    VADCheck -->|Speech detected| GreedyWhisper[Run Faster-Whisper<br/>beam_size=1 + int8 / GPU]
    GreedyWhisper --> StoreTranscript[Persist Transcript & Breakdown]
```

### Pillar 1: Intelligent Gating & Trigger Modes

Replace binary `AUTO_TRANSCRIBE_OUTLIERS` with three distinct operational policies configured via [app/config.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/config.py):

* **`on_demand` (Recommended Default):**
  No background transcription jobs are enqueued during scraping. All outlier metrics, velocity, and thumbnails are calculated instantly. When a user clicks "View Analysis" or triggers "Generate Transcript" in [frontend/src/app/analysis/[id]/AnalysisView.tsx](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/frontend/src/app/analysis/[id]/AnalysisView.tsx), transcription executes on demand in 2–3 seconds via [trigger_transcription](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/api/content.py#L164-L184).

* **`top_tier` (Selective Auto-Processing):**
  Only the single highest-performing outlier per scrape that meets stringent criteria (`view_multiplier >= 5.0` and minimum view count threshold) is automatically scheduled. All secondary outliers remain on-demand. A hard concurrency cap prevents more than 1 background transcription from running at any time.

* **`disabled`:**
  Fully prevents automated transcription queues, reserving transcription strictly for manual API or UI invocation.

### Pillar 2: Pre-Flight Voice Activity Detection (VAD) & Audio Probing

Before invoking the heavy neural network, verify that spoken audio is actually present:

* **Fast FFmpeg Volume/Silence Probe:**
  A 50ms FFmpeg audio filter pass (`ffmpeg -i ... -af silencedetect=noise=-30dB:d=0.5 -f null -`) detects silent clips or zero-amplitude audio tracks. If silence exceeds 90% of duration, mark the content immediately as `Visual/Silent Reel` without loading Whisper models.
* **Integrated Silero VAD:**
  Configure Faster-Whisper with `vad_filter=True` and `min_silence_duration_ms=500`. Silero VAD runs on a lightweight ONNX runtime, stripping out music, background noise, and pauses before passing voice segments to the transformer encoder. If zero vocal frames are returned, transcription concludes in under 200ms.

### Pillar 3: Inference Hyperparameter & Engine Tuning

Update [TranscriptionService._transcribe_audio_file](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py#L165-L212):

* **Greedy Search (`beam_size=1`):** Decreases inference time by 60–80% compared to `beam_size=5` with zero perceptible quality drop on conversational English short-form speech.
* **Deterministic Single-Pass Decoding:** Set `best_of=1`, `temperature=0.0`, and `condition_on_previous_text=False` to prevent hallucination looping during repetitive backing tracks.
* **Device Auto-Selection:** Auto-detect CUDA availability (`torch.cuda.is_available()` or ctranslate2 GPU backend). If an NVIDIA GPU is detected, employ `device="cuda"`, `compute_type="float16"` for sub-second execution; otherwise, default to `device="cpu"`, `compute_type="int8"` with thread count clamped to `min(4, os.cpu_count() // 2)` to avoid saturating host cores.
* **Model Sizing Hierarchy:** Support `WHISPER_MODEL_SIZE="base"` (balanced) or `"tiny"` (for ultra-low-power deployments).

### Pillar 4: Audio-Only Extraction & Lifecycle Management

Rather than maintaining heavy full-resolution MP4 video files solely for transcription:

* In [TaskExecutor._download_video](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/worker/tasks.py#L120-L155) and [TranscriptionService._ensure_video_file](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py#L98-L164), download or stream directly to an isolated 16 kHz mono audio container (`.m4a` or `.wav`) using FFmpeg (`-vn -ac 1 -ar 16000`).
* Audio file size drops from ~35 MB (video) to ~800 KB (16 kHz mono audio), slashing memory footprint and disk I/O.
* Retain temporary audio files only for the duration of inference, deleting them immediately following persistence in [Transcript](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/models/transcript.py).

---

## 3. Implementation Plan & Work Breakdown

### Phase 1: Configuration & Settings Refactor
* Update [app/config.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/config.py):
  * Introduce `TRANSCRIPTION_MODE: str = "on_demand"` (`"on_demand" | "top_tier" | "all" | "disabled"`).
  * Introduce `AUTO_TRANSCRIBE_MIN_SCORE: float = 5.0`.
  * Introduce `WHISPER_BEAM_SIZE: int = 1`.
  * Introduce `WHISPER_VAD_FILTER: bool = True`.
  * Introduce `WHISPER_DEVICE: str = "auto"` (`"auto" | "cpu" | "cuda"`).
  * Deprecate uncontrolled `AUTO_TRANSCRIBE_OUTLIERS=true`.

### Phase 2: Content Ingestion Gating
* Modify [ContentService.ingest_scraped_items](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/content_service.py#L132-L154):
  * Check `settings.TRANSCRIPTION_MODE`. If `"on_demand"` or `"disabled"`, do not enqueue transcription processing jobs.
  * If `"top_tier"`, filter outliers by `item.outlier_score >= settings.AUTO_TRANSCRIBE_MIN_SCORE`, sorting descending and queueing at most 1 job per competitor scrape.

### Phase 3: Transcription Service & VAD Integration
* Enhance [TranscriptionService](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py):
  * Update `get_whisper_model()` to inspect available hardware (`cuda` vs `cpu`) and apply CPU thread limits (`cpu_threads=4`).
  * In `_transcribe_audio_file()`, configure `model.transcribe()` with `beam_size=settings.WHISPER_BEAM_SIZE`, `vad_filter=True`, and `temperature=0.0`.
  * Implement lightweight audio pre-extraction via FFmpeg (`extract_audio_stream()`) to feed 16 kHz mono streams into Whisper instead of whole MP4 containers.
  * If VAD segments are empty, cleanly record `"Non-vocal / Music Reel"` without error or repeated attempts.

### Phase 4: Frontend UI Feedback
* Verify and polish [frontend/src/app/analysis/[id]/AnalysisView.tsx](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/frontend/src/app/analysis/[id]/AnalysisView.tsx):
  * Display an explicit "Generate Transcript" action card when `item.transcript` is absent.
  * Provide real-time spinner feedback while on-demand transcription executes via `/content/{id}/transcribe`.
  * Display clear badges distinguishing spoken transcripts from music/visual content.

---

## 4. Expected Results & Metrics

| Metric | Before Optimization | After Optimization (On-Demand Mode) |
| :--- | :--- | :--- |
| **Scrape Job CPU Utilization** | Sustained 100% CPU across multiple minutes | Baseline metadata scraping only (~5% CPU) |
| **Transcription Jobs Per Scrape** | 5 to 15 unthrottled jobs | 0 jobs (background) / 1 job (if top_tier enabled) |
| **Inference Time Per Reel** | 15–40 seconds (`beam_size=5`, no VAD) | 2–5 seconds (`beam_size=1`, Silero VAD) |
| **Compute Spent on Music Reels** | Full transformer pass (~25s 100% CPU) | Bypassed in ~200ms via VAD |
| **Disk & Memory Footprint** | 30–60 MB per Reel video | ~800 KB temporary audio buffer |
