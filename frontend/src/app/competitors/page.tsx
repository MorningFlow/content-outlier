"use client";

import { useState, useEffect, useTransition, useCallback } from "react";
import Link from "next/link";
import { api, CompetitorRecord, resolveMedia } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface ActiveSyncState {
  username: string;
  jobId: string;
  status: string; // queued, running, completed, failed
  percent: number;
  stage: string;
  error?: string | null;
}

export default function CompetitorsPage() {
  const [competitors, setCompetitors] = useState<CompetitorRecord[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [syncState, setSyncState] = useState<ActiveSyncState | null>(null);
  const [isPending, startTransition] = useTransition();

  const load = useCallback(() => {
    api.competitors.list()
      .then((data) => {
        setCompetitors(data);
        setLoadError(null);
      })
      .catch((err) => {
        console.error(err);
        setLoadError(err instanceof Error ? err.message : "Failed to load competitors from API");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll competitors list every 1.5 seconds if any competitor has an active background job
  const hasActiveSync = competitors.some(
    (c) => c.active_job && (c.active_job.status === "queued" || c.active_job.status === "running")
  );

  useEffect(() => {
    if (!hasActiveSync) return;
    const interval = setInterval(() => {
      load();
    }, 1500);
    return () => clearInterval(interval);
  }, [hasActiveSync, load]);

  // Poll detailed job progress when modal is tracking a specific sync
  useEffect(() => {
    if (!syncState || syncState.status === "completed" || syncState.status === "failed") {
      return;
    }

    const timer = setInterval(async () => {
      try {
        const job = await api.jobs.get(syncState.jobId);
        setSyncState((prev) => {
          if (!prev) return null;
          return {
            ...prev,
            status: job.status,
            percent: job.progress_percent ?? (job.status === "completed" ? 100 : prev.percent),
            stage: job.progress_stage || (job.status === "completed" ? "Completed! Profile & posts tracked." : prev.stage),
            error: job.error_message,
          };
        });

        if (job.status === "completed" || job.status === "failed") {
          load();
        }
      } catch (err) {
        console.error("Job poll error:", err);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [syncState?.jobId, syncState?.status, load]);

  // Automatically close modal 2.5s after 100% completion
  useEffect(() => {
    if (syncState?.status === "completed") {
      const timer = setTimeout(() => {
        setShowModal(false);
        setSyncState(null);
        load();
      }, 2500);
      return () => clearTimeout(timer);
    }
  }, [syncState?.status, load]);

  async function addCompetitor() {
    const clean = username.trim().replace(/^@/, "");
    if (!clean || isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const res = await api.competitors.add(clean);
      const initialPercent = res.job?.progress_percent || 5;
      const initialStage = res.job?.progress_stage || "Queued for synchronization...";
      setSyncState({
        username: clean,
        jobId: res.job.id,
        status: res.job.status || "queued",
        percent: initialPercent,
        stage: initialStage,
      });
      setUsername("");
      load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function syncCompetitor(id: string, name: string) {
    try {
      const job = await api.competitors.sync(id);
      load();
      setSyncState({
        username: name,
        jobId: job.id,
        status: job.status || "queued",
        percent: job.progress_percent || 5,
        stage: job.progress_stage || "Queued for synchronization...",
      });
      setShowModal(true);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Sync failed");
    }
  }

  async function deleteCompetitor(id: string, name: string) {
    if (!confirm(`Stop tracking @${name}?`)) return;
    startTransition(async () => {
      await api.competitors.delete(id);
      load();
    });
  }

  return (
    <>
      <h1 className="page-title">Competitors</h1>
      <p className="page-sub">Manage the Instagram accounts Content Outlier monitors.</p>

      {loadError && (
        <div style={{
          background: "var(--signal-bg, #2A2013)",
          color: "var(--signal, #E0A458)",
          border: "1px solid var(--signal, #E0A458)",
          padding: "10px 14px",
          borderRadius: 4,
          marginBottom: 16,
          fontSize: 13,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between"
        }}>
          <span>⚠️ {loadError}</span>
          <button className="btn" style={{ fontSize: 11.5, padding: "4px 8px" }} onClick={load}>Retry</button>
        </div>
      )}

      <div className="section-head">
        <span />
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowModal(true);
            setSyncState(null);
            setError(null);
          }}
        >
          + Add Competitor
        </button>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Account</th>
              <th>Followers</th>
              <th>Content Tracked</th>
              <th>Last Scanned</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {competitors.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: "center", color: "var(--ink-soft)", padding: 32 }}>
                  {loadError ? "Cannot load competitors while backend is offline." : "No competitors yet."}
                </td>
              </tr>
            ) : (
              competitors.map((c) => {
                const isActive = c.is_active ?? (c.status === "active");
                const hasJob = Boolean(c.active_job && (c.active_job.status === "queued" || c.active_job.status === "running"));
                const jobPercent = c.active_job?.progress_percent ?? 0;
                const jobStage = c.active_job?.progress_stage;

                return (
                  <tr key={c.id}>
                    <td>
                      <div className="row-user" style={{ display: "flex", alignItems: "center" }}>
                        {c.profile_image ? (
                          <img
                            src={resolveMedia(c.profile_image)!}
                            alt={c.username}
                            style={{ width: 24, height: 24, borderRadius: "50%", marginRight: 8, objectFit: "cover" }}
                          />
                        ) : (
                          <span className="avatar" style={{ width: 24, height: 24, marginRight: 8 }} />
                        )}
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>@{c.username}</div>
                          {c.profile_name && (
                            <div style={{ fontSize: 11, color: "var(--ink-soft)" }}>{c.profile_name}</div>
                          )}
                          {hasJob && jobStage && (
                            <div style={{ fontSize: 11, color: "var(--accent, #60a5fa)", marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
                              <span>•</span>
                              <span>{jobStage}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {(c.follower_count ?? c.followers)?.toLocaleString() ?? "—"}
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {c.content_count}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                      {c.last_scraped_at
                        ? formatDate(c.last_scraped_at)
                        : (hasJob ? "Syncing now..." : "Never")}
                    </td>
                    <td>
                      {hasJob ? (
                        <div style={{ minWidth: 120 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11.5, marginBottom: 3 }}>
                            <span style={{ color: "var(--accent, #60a5fa)", fontWeight: 600 }}>Syncing</span>
                            <span className="mono" style={{ fontSize: 11, fontWeight: 600 }}>{jobPercent}%</span>
                          </div>
                          <div style={{ width: "100%", height: 5, background: "var(--line, rgba(255,255,255,0.1))", borderRadius: 3, overflow: "hidden" }}>
                            <div style={{
                              width: `${Math.min(100, Math.max(0, jobPercent))}%`,
                              height: "100%",
                              background: "linear-gradient(90deg, #3b82f6, #60a5fa)",
                              transition: "width 0.35s ease-in-out"
                            }} />
                          </div>
                        </div>
                      ) : c.status === "needs_auth" ? (
                        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                          <span className="status-dot" style={{ background: "#f59e0b" }} />
                          <Link
                            href="/settings"
                            style={{
                              fontSize: 12,
                              color: "#f59e0b",
                              textDecoration: "underline",
                              fontWeight: 500,
                            }}
                            title={c.scrape_error || "Instagram session required to query Reels. Connect your account in Settings."}
                          >
                            Needs Session
                          </Link>
                        </div>
                      ) : (
                        <>
                          <span className="status-dot" style={isActive ? {} : { background: "var(--ink-soft)" }} />
                          <span style={{ fontSize: 12 }}>{isActive ? "Active" : c.status === "rate_limited" ? "Rate Limited" : c.status === "error" ? "Error" : "Paused"}</span>
                        </>
                      )}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button
                        className="btn"
                        style={{ fontSize: 11.5, marginRight: 6 }}
                        disabled={hasJob}
                        onClick={() => syncCompetitor(c.id, c.username)}
                      >
                        {hasJob ? `${jobPercent}%` : "Sync now"}
                      </button>
                      <button
                        className="btn"
                        style={{ fontSize: 11.5, color: "var(--signal)" }}
                        onClick={() => deleteCompetitor(c.id, c.username)}
                        disabled={isPending || hasJob}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Add Competitor / Live Progress Modal */}
      {showModal && (
        <div
          className="overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isSubmitting) {
              setShowModal(false);
            }
          }}
        >
          <div className="modal" style={{ maxWidth: 440 }}>
            {syncState ? (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <div>
                    <h3 style={{ margin: "0 0 2px", fontSize: 16 }}>@{syncState.username}</h3>
                    <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                      {syncState.status === "completed"
                        ? "Synchronization finished"
                        : syncState.status === "failed"
                        ? "Synchronization encountered an issue"
                        : "Collecting Instagram content & baselines"}
                    </div>
                  </div>
                  <span
                    className="mono"
                    style={{
                      fontSize: 16,
                      fontWeight: 700,
                      color:
                        syncState.status === "failed"
                          ? "var(--signal)"
                          : syncState.percent >= 100
                          ? "#10b981"
                          : "var(--accent, #60a5fa)",
                    }}
                  >
                    {syncState.percent}%
                  </span>
                </div>

                {/* Progress bar container */}
                <div
                  style={{
                    width: "100%",
                    height: 8,
                    background: "var(--line, rgba(255,255,255,0.1))",
                    borderRadius: 4,
                    overflow: "hidden",
                    marginBottom: 14,
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, Math.max(0, syncState.percent))}%`,
                      height: "100%",
                      background:
                        syncState.status === "failed"
                          ? "var(--signal, #ef4444)"
                          : syncState.percent >= 100
                          ? "#10b981"
                          : "linear-gradient(90deg, #3b82f6, #60a5fa)",
                      transition: "width 0.35s ease-in-out",
                      borderRadius: 4,
                    }}
                  />
                </div>

                {/* Live Stage Description */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: 12.5,
                    color: "var(--ink)",
                    marginBottom: 16,
                    background: "rgba(255, 255, 255, 0.04)",
                    padding: "10px 12px",
                    borderRadius: 6,
                    border: "1px solid var(--line, rgba(255, 255, 255, 0.08))",
                  }}
                >
                  {syncState.status === "running" || syncState.status === "queued" ? (
                    <span
                      className="status-dot"
                      style={{
                        background: "var(--accent, #60a5fa)",
                        boxShadow: "0 0 8px rgba(96, 165, 250, 0.6)",
                      }}
                    />
                  ) : syncState.status === "completed" ? (
                    <span style={{ color: "#10b981", fontSize: 14, fontWeight: "bold" }}>✓</span>
                  ) : (
                    <span style={{ color: "var(--signal)", fontSize: 14 }}>⚠️</span>
                  )}
                  <span style={{ flex: 1, fontWeight: 500 }}>{syncState.stage || "Synchronizing profile..."}</span>
                </div>

                {syncState.error && (
                  <p style={{ color: "var(--signal)", fontSize: 12, marginBottom: 14, lineHeight: 1.4 }}>
                    {syncState.error}
                  </p>
                )}

                <p style={{ fontSize: 11.5, color: "var(--ink-soft)", margin: "0 0 16px", lineHeight: 1.4 }}>
                  {syncState.status === "completed"
                    ? "Initial synchronization complete. All posts, performance metrics, and median baselines have been ingested."
                    : "You can dismiss this modal anytime; sync will run seamlessly in the background and update the table below."}
                </p>

                <div className="modal-actions">
                  <button
                    className="btn"
                    onClick={() => {
                      setShowModal(false);
                      setSyncState(null);
                    }}
                  >
                    {syncState.status === "completed" ? "Done" : "Run in Background"}
                  </button>
                  {syncState.status !== "completed" && (
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        setShowModal(false);
                      }}
                    >
                      View Table
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div>
                <h3>Add Competitor</h3>
                <p style={{ margin: "4px 0 12px", fontSize: 13, color: "var(--ink-soft)" }}>
                  Enter an Instagram username or paste any Reel / Post URL to track their content.
                </p>
                {error && (
                  <p style={{ color: "var(--signal)", fontSize: 12, marginBottom: 8, lineHeight: 1.4 }}>{error}</p>
                )}
                <input
                  type="text"
                  placeholder="e.g. @nivedan.ai or instagram.com/reel/..."
                  value={username}
                  disabled={isSubmitting}
                  onChange={(e) => setUsername(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addCompetitor()}
                  autoFocus
                />
                <div style={{ fontSize: 11.5, color: "var(--ink-soft)", marginTop: 6, lineHeight: 1.4 }}>
                  💡 <span style={{ color: "var(--ink-muted)" }}>Tip:</span> Pasting a direct Reel URL auto-anchors the creator&apos;s verified profile ID and avatar without requiring an active session.
                </div>
                <div className="modal-actions" style={{ marginTop: 16 }}>
                  <button
                    className="btn"
                    disabled={isSubmitting}
                    onClick={() => {
                      setShowModal(false);
                      setError(null);
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={addCompetitor}
                    disabled={isSubmitting || !username.trim()}
                  >
                    {isSubmitting ? "Adding..." : "Add Competitor"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
