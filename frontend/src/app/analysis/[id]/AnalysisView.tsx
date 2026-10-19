"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ContentDetailItem, TranscriptResponse, resolveMedia } from "@/lib/api";
import { fmt, formatDate } from "@/lib/format";
import { VideoPlayer } from "@/components/VideoPlayer";

interface Props {
  item: ContentDetailItem;
}

export function AnalysisView({ item }: Props) {
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(item.transcript);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const videoSrc = resolveMedia(item.video_path ?? (item.video_url?.startsWith("/media/") ? item.video_url : null));
  const posterSrc = resolveMedia(item.thumbnail_url);
  const reasons = item.outlier_reasons as Record<string, unknown> | null;

  async function handleGenerateTranscript() {
    setIsGenerating(true);
    setError(null);
    try {
      const res = await api.content.transcribe(item.id);
      setTranscript(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate transcript");
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleCopy() {
    if (!transcript) return;
    let textToCopy = "";
    if (transcript.segments && transcript.segments.length > 0) {
      textToCopy = transcript.segments
        .map((s) => {
          const mins = Math.floor(s.start / 60);
          const secs = Math.floor(s.start % 60)
            .toString()
            .padStart(2, "0");
          return `[${mins}:${secs}] ${s.text}`;
        })
        .join("\n");
    } else {
      textToCopy = transcript.full_text || "";
    }

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error("Clipboard copy failed:", e);
    }
  }

  return (
    <>
      <Link className="back-link" href="/outliers">
        ← Back to Outliers
      </Link>
      <h1 className="page-title" style={{ marginBottom: 2 }}>
        {item.outlier_score}× Outlier
      </h1>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
        <img
          src={resolveMedia(`/media/profiles/${item.instagram_username}.jpg`)!}
          onError={(e) => {
            (e.target as HTMLElement).style.display = "none";
          }}
          alt={item.instagram_username}
          style={{ width: 28, height: 28, borderRadius: "50%", objectFit: "cover" }}
        />
        <p className="page-sub" style={{ margin: 0 }}>
          @{item.instagram_username} · Posted {formatDate(item.published_at)}
        </p>
      </div>

      <div className="analysis-grid">
        {/* Left col — player */}
        <div>
          <VideoPlayer
            src={videoSrc}
            poster={posterSrc}
            shortcode={item.shortcode}
            instagramUrl={item.instagram_url}
          />
          <a className="analysis-link" href={item.instagram_url} target="_blank" rel="noopener noreferrer">
            View on Instagram ↗
          </a>
        </div>

        {/* Right col — stats + transcript */}
        <div>
          <div className="stat-list">
            <div className="row"><span>Outlier Score</span><span>{item.outlier_score}×</span></div>
            <div className="row"><span>Views</span><span>{fmt(item.view_count)}</span></div>
            <div className="row">
              <span>Account Baseline</span>
              <span>{fmt((reasons?.account_baseline_views as number | null) ?? null)}</span>
            </div>
            <div className="row"><span>Likes</span><span>{fmt(item.like_count)}</span></div>
            <div className="row"><span>Comments</span><span>{fmt(item.comment_count)}</span></div>
            <div className="row">
              <span>Content Age</span>
              <span>{reasons ? `${(reasons.age_days as number) ?? "—"} days` : "Recent"}</span>
            </div>
          </div>

          {/* Transcript Section */}
          {transcript ? (
            <div className="transcript-box">
              <div className="transcript-header">
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>Audio Transcript</span>
                  {transcript.segments && transcript.segments.length > 0 ? (
                    <span className="transcript-count">
                      {transcript.segments.length} segments
                    </span>
                  ) : (
                    <span className="transcript-count" style={{ color: "var(--ink-soft)" }}>
                      Non-vocal
                    </span>
                  )}
                </div>
                <button
                  className={`btn-copy ${copied ? "copied" : ""}`}
                  onClick={handleCopy}
                  title="Copy full transcript to clipboard"
                  type="button"
                >
                  {copied ? (
                    <>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span style={{ color: "#10b981", fontWeight: 600 }}>Copied</span>
                    </>
                  ) : (
                    <>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                      <span>Copy Transcript</span>
                    </>
                  )}
                </button>
              </div>

              <div className="transcript">
                {transcript.segments && transcript.segments.length > 0 ? (
                  transcript.segments.map((s, i) => {
                    const mins = Math.floor(s.start / 60);
                    const secs = Math.floor(s.start % 60)
                      .toString()
                      .padStart(2, "0");
                    return (
                      <div key={i} className="transcript-line">
                        <span className="ts">{mins}:{secs}</span>
                        <span className="txt">{s.text}</span>
                      </div>
                    );
                  })
                ) : (
                  <div style={{ padding: "8px 0", color: "var(--ink-soft)", fontStyle: "italic", fontSize: 12.5 }}>
                    {transcript.full_text || "No spoken dialogue detected in this video."}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="transcript-empty-card">
              <div className="transcript-empty-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" x2="12" y1="19" y2="22" />
                </svg>
              </div>
              <div className="transcript-empty-title">Audio Transcript</div>
              <p className="transcript-empty-desc">
                Extract exact timestamped speech segments directly from this Reel&apos;s audio stream.
              </p>
              {error && <div className="transcript-error">{error}</div>}
              <button
                className="btn btn-primary"
                onClick={handleGenerateTranscript}
                disabled={isGenerating}
                style={{ minWidth: 200 }}
                type="button"
              >
                {isGenerating ? (
                  <>
                    <span className="spinner-sm" /> Transcribing Reel audio...
                  </>
                ) : (
                  <>Generate Transcript</>
                )}
              </button>
            </div>
          )}

          <div className="cta-row">
            <button className="btn btn-primary" type="button">Create My Version →</button>
          </div>
        </div>
      </div>
    </>
  );
}
