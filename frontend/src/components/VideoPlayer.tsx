"use client";

import { useState } from "react";

/** Client wrapper for both local video playback and official Instagram live embed iframe. */
interface Props {
  src?: string | null;
  poster?: string | null;
  shortcode?: string | null;
  instagramUrl?: string | null;
}

export function VideoPlayer({ src, poster, shortcode, instagramUrl }: Props) {
  // Extract shortcode from instagramUrl if not explicitly provided
  let effectiveShortcode = shortcode;
  if (!effectiveShortcode && instagramUrl) {
    const match = instagramUrl.match(/(?:reel|p)\/([A-Za-z0-9_-]+)/);
    if (match) {
      effectiveShortcode = match[1];
    }
  }

  // Default to iframe embed if no local src is available, or if embed is requested
  const hasLocalVideo = Boolean(src);
  const hasEmbed = Boolean(effectiveShortcode);
  const [playerMode, setPlayerMode] = useState<"embed" | "local">(
    hasEmbed ? "embed" : "local"
  );

  if (!hasLocalVideo && !hasEmbed) {
    return (
      <div className="player" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "var(--ink-soft)", fontSize: 12 }}>Video not available</span>
      </div>
    );
  }

  return (
    <div className="player-container" style={{ position: "relative", width: "100%", marginBottom: 16 }}>
      {/* Player Mode Toggle when both local copy and live Instagram embed are available */}
      {hasLocalVideo && hasEmbed && (
        <div
          style={{
            display: "flex",
            gap: 8,
            marginBottom: 8,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={() => setPlayerMode("embed")}
            style={{
              padding: "4px 10px",
              fontSize: 11,
              borderRadius: 6,
              border: playerMode === "embed" ? "1px solid var(--accent, #6366f1)" : "1px solid var(--line, #333)",
              background: playerMode === "embed" ? "rgba(99, 102, 241, 0.15)" : "transparent",
              color: playerMode === "embed" ? "var(--accent, #6366f1)" : "var(--ink-soft, #888)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Instagram Embed
          </button>
          <button
            type="button"
            onClick={() => setPlayerMode("local")}
            style={{
              padding: "4px 10px",
              fontSize: 11,
              borderRadius: 6,
              border: playerMode === "local" ? "1px solid var(--accent, #6366f1)" : "1px solid var(--line, #333)",
              background: playerMode === "local" ? "rgba(99, 102, 241, 0.15)" : "transparent",
              color: playerMode === "local" ? "var(--accent, #6366f1)" : "var(--ink-soft, #888)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Local MP4
          </button>
        </div>
      )}

      {/* Official Instagram Live Embed Iframe */}
      {playerMode === "embed" && hasEmbed ? (
        <div
          className="player"
          style={{
            position: "relative",
            width: "100%",
            borderRadius: 12,
            overflow: "hidden",
            boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
            background: "#000",
            minHeight: "560px",
          }}
        >
          <iframe
            src={`https://www.instagram.com/reel/${effectiveShortcode}/embed/`}
            style={{
              width: "100%",
              height: "560px",
              border: "none",
              display: "block",
            }}
            allow="autoplay; clipboard-write; encrypted-media; picture-in-picture; web-share"
            allowFullScreen
            scrolling="no"
            title={`Instagram Reel ${effectiveShortcode}`}
          />
        </div>
      ) : (
        /* Local HTML5 Video Player */
        <div className="player">
          <video
            src={src ?? undefined}
            poster={poster ?? undefined}
            controls
            autoPlay
            muted
            loop
            playsInline
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block", borderRadius: 12 }}
          >
            Your browser does not support HTML5 video.
          </video>
        </div>
      )}
    </div>
  );
}
