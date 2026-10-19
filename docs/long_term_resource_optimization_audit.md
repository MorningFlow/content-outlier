# Long-Term Resource Optimization Audit: Content Outlier

## Executive Summary

This audit assesses the long-term resource efficiency of the Content Outlier application across disk storage, database scalability, CPU/RAM utilization, and network bandwidth. The audit identifies architectural bottlenecks that emerge as tracked competitor counts and historical timelines scale, and establishes concrete technical optimizations to reduce steady-state resource consumption by over 80%.

---

## 1. Disk Storage & Media Lifecycle (Critical Risk)

### Current Behavior
In [TaskExecutor._download_video](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/worker/tasks.py#L120-L155) and [TranscriptionService._ensure_video_file](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py#L141-L165), whenever an outlier is flagged or transcribed:
1. The full 1080p MP4 video file (typically 15 MB – 45 MB) is downloaded.
2. The file is saved permanently to VPS disk under `media_storage/videos/{username}/{shortcode}.mp4`.
3. There is no Time-to-Live (TTL), garbage collection, or disk quota management.

### Growth Projection
- 20 monitored competitors $\times$ 10 outliers each = 200 videos $\approx$ **6 GB to 9 GB**.
- 50 monitored competitors over 6 months = 1,000+ outliers $\approx$ **35 GB to 50 GB**, which exceeds the entire available disk space (31 GB) on your Oracle Cloud VPS.

### Recommended Optimizations
1. **Audio-Only Extraction for Transcription**: Faster-Whisper only requires 16 kHz mono audio (~500 KB to 1 MB per Reel). Modify the downloader to extract audio directly via FFmpeg (`-vn -ac 1 -ar 16000`), immediately eliminating **95% of download bandwidth and disk usage**.
2. **Ephemeral Transcription Storage**: Delete the temporary audio file immediately after the transcript is written to the database in [Transcript](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/models/transcript.py).
3. **Offload Persistent Media to Supabase S3**: For thumbnails and profile images that the frontend displays, configure `STORAGE_BACKEND=s3` using Supabase Storage S3 credentials in [.env](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/.env#L14-L16). The VPS disk remains virtually stateless (<500 MB).
4. **Automated Pruning Job**: Implement a daily cron task in [scheduler.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/worker/scheduler.py) that deletes local cached media files older than 14 days whose status is already completed.

---

## 2. Database Growth & Snapshot Bloat (Supabase / PostgreSQL)

### Current Behavior
In [ContentService.ingest_scraped_items](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/content_service.py#L84-L108):
- Every scan (default every 6 hours) creates an immutable record in `content_metrics` for every post returned by the scraper.
- An account's older posts whose view and like counts have plateaued continue receiving redundant snapshot rows every 6 hours indefinitely.

### Growth Projection
- 20 competitors $\times$ 50 posts = 1,000 posts.
- 4 scans per day = 4,000 rows/day = **120,000 rows/month** in `content_metrics`.
- Within 1 year, this table accumulates over 1.4 million rows with corresponding B-tree index bloat on Supabase.

### Recommended Optimizations
1. **Delta-Gated Snapshots**: Only insert a new `ContentMetric` record if:
   - View count has changed by $\ge 1.0\%$, OR
   - At least 48 hours have elapsed since the last recorded snapshot (for baseline trend confirmation).
2. **Post Lifecycle Decay**: Posts older than 30 days rarely show view velocity changes. Limit the incremental scraper to the 10 most recent posts for mature accounts unless the account published a new post.
3. **Metric Downsampling**: Maintain hourly/6-hourly granularity for the first 14 days, and downsample historical snapshots older than 60 days to one record per week.

---

## 3. Worker Polling & Connection Churn

### Current Behavior
In [app.worker.runner.run_worker](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/worker/runner.py#L58-L76):
```python
while _running:
    had_work = process_single_job()
    if not had_work:
        time.sleep(poll_interval) # fixed at 5.0 seconds
```
Every 5 seconds, the worker establishes a database connection, performs two table queries (`ScrapeJob` and `ProcessingJob`), and closes the session.

### Resource Impact
- When the queue is empty, the worker executes **12 DB roundtrips/minute** = **720 connections/hour** = **17,280 queries/day** against Supabase's connection pooler.

### Recommended Optimizations
1. **Adaptive Exponential Backoff**: When no jobs are found, incrementally increase `poll_interval` from 5s $\to$ 10s $\to$ 20s $\to$ 30s. Reset immediately to 1s upon finding work. This cuts idle database queries by **80%**.
2. **Persistent Connection Session**: Rather than tearing down and reconstructing `SessionLocal()` on every empty cycle, reuse a shared worker session with lightweight transaction rollbacks.

---

## 4. Compute & Algorithmic Complexity

### Current Behavior
In [ContentService.ingest_scraped_items](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/content_service.py#L112-L131):
```python
all_competitor_contents = self.db.query(Content).filter(Content.competitor_id == competitor.id).all()
base_views, base_eng = self.outlier_engine.compute_competitor_baseline(all_competitor_contents)
# Re-evaluate outlier scores for all contents with updated baseline
for item in all_competitor_contents:
    eval_res = self.outlier_engine.evaluate_content(item, competitor)
    ...
```
Every time a sync completes, all historical posts for that competitor are loaded into Python memory, the median is calculated in Python, and every post is sequentially updated.

### Recommended Optimizations
1. **Windowed Baseline Calculation**: Calculate median baselines over the most recent 50 posts or 90-day window rather than all historical records.
2. **SQL-Native Median**: Compute the baseline view median directly in PostgreSQL using `percentile_cont(0.5) WITHIN GROUP (ORDER BY view_count)` instead of pulling thousands of ORM objects into Python memory.
3. **Dirty-Flag Outlier Updates**: Only re-evaluate items whose metrics changed in the current scrape, rather than updating every row in the database.

---

## 5. Machine Learning & Speech Inference Tuning

### Current Settings vs. Optimal
In [app/config.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/config.py#L39-L45):
- `TRANSCRIPTION_MODE=on_demand` is already configured, which successfully avoids background CPU saturation.
- `WHISPER_MODEL_SIZE="base"` (~250 MB RAM). For short-form social media speech where captions exist or high nuance is not needed, `WHISPER_MODEL_SIZE="tiny"` reduces RAM to ~120 MB and speeds up inference by 2.5x.
- Clamping `WHISPER_CPU_THREADS=2` ensures inference never starves `n8n` or other VPS background processes.
- **Model Unloading TTL**: The `_whisper_model` instance in [get_whisper_model](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/services/transcription_service.py#L22) currently stays in RAM permanently after its first execution. Adding an idle timeout (e.g. unload model if no transcription occurs for 10 minutes) frees 250 MB RAM back to the operating system.

---

## Implementation Priority Matrix

| Priority | Optimization Item | Primary Impact | Implementation Complexity |
|---|---|---|---|
| **P0** | Audio-only extraction + immediate cleanup | Slashes disk usage by 95% | Low (modify FFmpeg command in `tasks.py`) |
| **P0** | Delta-gated `content_metrics` snapshots | Reduces Supabase row growth by 85% | Low (add threshold check in `content_service.py`) |
| **P1** | Worker adaptive polling backoff | Reduces idle DB queries from 17k/day to 2k/day | Low (5 lines in `runner.py`) |
| **P1** | Supabase S3 bucket offload | Keeps VPS disk 100% stateless | Medium (configure `.env` S3 credentials) |
| **P2** | Windowed baseline computation | Eliminates $O(N)$ ORM memory bloat | Medium (adjust `content_service.py` query) |
| **P2** | Whisper model lazy unload / tiny default | Frees ~250 MB RAM during idle periods | Low (adjust `app/config.py` and `transcription_service.py`) |
