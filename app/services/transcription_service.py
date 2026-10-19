import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Any
import httpx
import instaloader
import time
import gc
import tempfile
import ctranslate2
from sqlalchemy.orm import Session
from faster_whisper import WhisperModel

from app.config import settings
from app.models.content import Content
from app.models.transcript import Transcript
from app.storage import get_storage

logger = logging.getLogger(__name__)

_whisper_model: Optional[WhisperModel] = None
_whisper_last_used: float = 0.0


def get_whisper_model() -> WhisperModel:
    """Lazily initializes and returns the shared WhisperModel instance with optimal device/threading."""
    global _whisper_model, _whisper_last_used
    _whisper_last_used = time.time()
    if _whisper_model is None:
        device = settings.WHISPER_DEVICE
        if device == "auto":
            try:
                has_cuda = ctranslate2.get_cuda_device_count() > 0
                device = "cuda" if has_cuda else "cpu"
            except Exception:
                device = "cpu"

        compute_type = "float16" if device == "cuda" else "int8"
        cpu_threads = min(settings.WHISPER_CPU_THREADS, max(1, (os.cpu_count() or 4) // 2))

        logger.info(
            f"Initializing faster-whisper {settings.WHISPER_MODEL_SIZE} model "
            f"(device={device}, compute_type={compute_type}, cpu_threads={cpu_threads})..."
        )
        _whisper_model = WhisperModel(
            settings.WHISPER_MODEL_SIZE,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
    return _whisper_model


def check_and_unload_whisper_model(max_idle_seconds: Optional[int] = None) -> bool:
    """Unloads the WhisperModel from memory if idle longer than max_idle_seconds to free RAM."""
    global _whisper_model, _whisper_last_used
    ttl = max_idle_seconds or settings.WHISPER_IDLE_TTL_SECONDS
    if _whisper_model is not None and (time.time() - _whisper_last_used) > ttl:
        logger.info(f"Unloading faster-whisper model from memory (idle > {ttl}s)...")
        _whisper_model = None
        gc.collect()
        return True
    return False


def has_audio_stream(file_path: Path) -> bool:
    """Rapid pre-flight check via ffprobe to detect if a valid media file contains an audio stream."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            # Unparseable file format or dummy test buffer; fallback to True
            return True
        return "audio" in res.stdout.lower()
    except Exception as e:
        logger.debug(f"ffprobe check error or missing for {file_path}: {e}")
        return True


class TranscriptionService:
    """Handles audio transcription via faster-whisper speech-to-text pipeline."""

    def __init__(self, db: Session):
        self.db = db
        self._temp_files: set[str] = set()

    def transcribe_content(self, content_id: str) -> Optional[Transcript]:
        """Runs the genuine speech-to-text transcription pipeline on a Reel video."""
        content = self.db.query(Content).filter(Content.id == content_id).first()
        if not content:
            logger.error(f"Content {content_id} not found for transcription.")
            return None

        # Check if already transcribed
        existing = self.db.query(Transcript).filter(Transcript.content_id == content.id).first()
        if existing:
            return existing

        video_file = self._ensure_video_file(content)

        try:
            if video_file and video_file.is_file():
                try:
                    transcript_data = self._transcribe_audio_file(video_file, fallback_duration=content.video_duration)
                except Exception as e:
                    logger.error(f"Whisper inference error on {video_file} for shortcode {content.shortcode}: {e}")
                    transcript_data = {
                        "full_text": f"Audio transcription could not be processed: {e}",
                        "language": "en",
                        "duration": content.video_duration or 0.0,
                        "segments": [],
                    }
            else:
                # If video file could not be downloaded/resolved, display caption if available or notice
                if content.caption:
                    transcript_data = {
                        "full_text": content.caption,
                        "language": "en",
                        "duration": content.video_duration or 0.0,
                        "segments": [],
                        "hook_text": content.caption.split("\n")[0][:120],
                    }
                else:
                    transcript_data = {
                        "full_text": "Video audio could not be retrieved from Instagram CDN.",
                        "language": "en",
                        "duration": content.video_duration or 0.0,
                        "segments": [],
                    }
        finally:
            # Ephemeral cleanup: remove temporary media files to prevent VPS disk saturation
            if video_file and str(video_file) in self._temp_files:
                try:
                    video_file.unlink(missing_ok=True)
                    self._temp_files.discard(str(video_file))
                    logger.info(f"Cleaned up ephemeral media file {video_file} after transcription.")
                except Exception as e:
                    logger.debug(f"Could not remove temp media {video_file}: {e}")

        transcript = Transcript(
            content_id=content.id,
            full_text=transcript_data["full_text"],
            language=transcript_data.get("language", "en"),
            duration=transcript_data.get("duration") or content.video_duration or 0.0,
            segments=transcript_data.get("segments", []),
            hook_text=transcript_data.get("hook_text"),
            breakdown_hook=transcript_data.get("breakdown_hook"),
            breakdown_topic=transcript_data.get("breakdown_topic"),
            breakdown_format=transcript_data.get("breakdown_format"),
            breakdown_cta=transcript_data.get("breakdown_cta"),
            key_takeaways=transcript_data.get("key_takeaways"),
        )

        self.db.add(transcript)
        content.transcription_status = "completed"
        self.db.commit()
        self.db.refresh(transcript)
        logger.info(f"Transcription completed for content shortcode {content.shortcode}")
        return transcript

    def _ensure_video_file(self, content: Content) -> Optional[Path]:
        """Ensures the Reel video file is downloaded and present on disk."""
        storage = get_storage()

        # 1. Check if video already exists in local storage
        if content.video_path and storage.exists(content.video_path):
            if hasattr(storage, "_full_path"):
                p = storage._full_path(content.video_path)
                if p.is_file() and p.stat().st_size > 0:
                    return p
            else:
                p = settings.storage_path / content.video_path.lstrip("/\\")
                if p.is_file() and p.stat().st_size > 0:
                    return p

        # 2. Check if file exists under convention: media_storage/videos/{username}/{shortcode}.mp4
        username = content.instagram_username or "unknown"
        standard_path = settings.storage_path / "videos" / username / f"{content.shortcode}.mp4"
        if standard_path.is_file() and standard_path.stat().st_size > 0:
            content.video_path = f"videos/{username}/{content.shortcode}.mp4"
            content.download_status = "downloaded"
            self.db.commit()
            return standard_path

        # 3. Resolve genuine video URL from Instagram if missing or expired CDN link
        video_url = content.video_url
        if not video_url or "fbcdn.net" in (video_url or ""):
            try:
                loader = instaloader.Instaloader()
                post = instaloader.Post.from_shortcode(loader.context, content.shortcode)
                if post.is_video and post.video_url:
                    video_url = post.video_url
                    content.video_url = video_url
                    if not content.thumbnail_url and post.url:
                        content.thumbnail_url = post.url
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Could not resolve video_url via instaloader for {content.shortcode}: {e}")

        if not video_url:
            logger.warning(f"No video URL available to download for shortcode {content.shortcode}")
            return None

        # 4. Download video file (persistent if configured, otherwise ephemeral to conserve disk)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
        }

        try:
            with httpx.Client(timeout=60.0, follow_redirects=True, headers=headers) as client:
                resp = client.get(video_url)
                if resp.status_code == 200 and len(resp.content) > 0:
                    if settings.AUTO_DOWNLOAD_OUTLIERS:
                        standard_path.parent.mkdir(parents=True, exist_ok=True)
                        standard_path.write_bytes(resp.content)
                        content.video_path = f"videos/{username}/{content.shortcode}.mp4"
                        content.download_status = "downloaded"
                        self.db.commit()
                        logger.info(f"Successfully downloaded Reel video to {standard_path} ({len(resp.content)} bytes)")
                        return standard_path
                    else:
                        temp_file = Path(tempfile.gettempdir()) / f"co_transcribe_{content.shortcode}.mp4"
                        temp_file.write_bytes(resp.content)
                        self._temp_files.add(str(temp_file))
                        logger.info(f"Buffered ephemeral Reel media to {temp_file} ({len(resp.content)} bytes) for transcription")
                        return temp_file
                else:
                    logger.warning(f"Download HTTP {resp.status_code} for shortcode {content.shortcode}")
        except Exception as e:
            logger.error(f"Error downloading video for shortcode {content.shortcode}: {e}")

        return None

    def _transcribe_audio_file(self, video_path: Path, fallback_duration: Optional[float] = None) -> dict[str, Any]:
        """Runs faster-whisper speech-to-text inference with VAD filtering and greedy decoding."""
        # 1. Pre-flight check: verify media container actually has an audio stream
        if not has_audio_stream(video_path):
            logger.info(f"No audio stream found in {video_path}; marking as Silent Reel without Whisper inference.")
            return {
                "full_text": "No audio track present in this video (silent or visual-only content).",
                "language": "en",
                "duration": fallback_duration or 0.0,
                "segments": [],
                "hook_text": None,
                "breakdown_hook": None,
                "breakdown_topic": None,
                "breakdown_format": "Silent Reel",
                "breakdown_cta": None,
                "key_takeaways": "Visual video without an audio track.",
            }

        # 2. Optimized Whisper inference with Silero VAD and greedy decoding
        model = get_whisper_model()
        segments_iter, info = model.transcribe(
            str(video_path),
            beam_size=settings.WHISPER_BEAM_SIZE,
            best_of=1,
            temperature=0.0,
            vad_filter=settings.WHISPER_VAD_FILTER,
            vad_parameters=dict(min_silence_duration_ms=500),
            condition_on_previous_text=False,
        )

        segments = [
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
            for seg in segments_iter
            if seg.text.strip()
        ]

        duration = round(info.duration, 2) if info and info.duration else (fallback_duration or 0.0)
        language = info.language if info and info.language else "en"

        if not segments:
            return {
                "full_text": "No spoken dialogue detected in this video (music or non-vocal audio).",
                "language": language,
                "duration": duration,
                "segments": [],
                "hook_text": None,
                "breakdown_hook": None,
                "breakdown_topic": None,
                "breakdown_format": "Non-vocal / Music Reel",
                "breakdown_cta": None,
                "key_takeaways": "Visual or music-driven short without spoken audio.",
            }

        full_text = " ".join(s["text"] for s in segments).strip()
        hook_text = segments[0]["text"] if segments else None

        return {
            "full_text": full_text,
            "language": language,
            "duration": duration,
            "segments": segments,
            "hook_text": hook_text,
            "breakdown_hook": hook_text,
            "breakdown_topic": None,
            "breakdown_format": "Spoken Reel",
            "breakdown_cta": segments[-1]["text"] if len(segments) > 1 else None,
            "key_takeaways": None,
        }

