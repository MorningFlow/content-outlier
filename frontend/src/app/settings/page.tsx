"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";

interface InstagramStatus {
  configured: boolean;
  username: string | null;
  status: string;
  has_session: boolean;
  last_authenticated: string | null;
  error_message: string | null;
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [igStatus, setIgStatus] = useState<InstagramStatus | null>(null);

  // Tab: "password" or "cookie"
  const [authMethod, setAuthMethod] = useState<"password" | "cookie">("password");

  // Input states & refs (refs ensure autofilled values are never missed)
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const sessionIdRef = useRef<HTMLInputElement>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRenewing, setIsRenewing] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // App settings state
  const [autoDownload, setAutoDownload] = useState(false);

  const loadStatus = async () => {
    try {
      const res = await api.settings.getInstagram();
      setIgStatus(res);
      if (res.username) {
        setUsername(res.username);
      }
    } catch (err: unknown) {
      console.warn("Failed to load Instagram settings:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleConnectPassword = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    // Read from state or DOM ref to handle browser autofill gracefully
    const currentUsername = (username || usernameRef.current?.value || "").trim().replace(/^@/, "");
    const currentPassword = password || passwordRef.current?.value || "";

    if (!currentUsername) {
      setMessage({ type: "error", text: "Please enter your Instagram username." });
      return;
    }
    if (!currentPassword) {
      setMessage({ type: "error", text: "Please enter your Instagram password." });
      return;
    }

    setIsSubmitting(true);
    setMessage(null);

    try {
      const res = await api.settings.connectInstagram({
        username: currentUsername,
        password: currentPassword,
      });

      if (res.success) {
        setMessage({
          type: "success",
          text: res.message || `Successfully connected @${currentUsername}. Session active & auto-renewing.`,
        });
        setPassword("");
        if (passwordRef.current) passwordRef.current.value = "";
        await loadStatus();
      } else {
        let msg = res.message || "Authentication failed.";
        if (msg.includes("Checkpoint required")) {
          msg = "Instagram triggered a security checkpoint challenge for server login. Switch to the 'Session Cookie' tab above to connect instantly using your browser cookie!";
        }
        setMessage({ type: "error", text: msg });
      }
    } catch (err: unknown) {
      const errDetail = err instanceof Error ? err.message : "Error connecting account";
      setMessage({ type: "error", text: errDetail });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConnectCookie = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    const currentUsername = (username || usernameRef.current?.value || "").trim().replace(/^@/, "");
    const currentSessionId = (sessionId || sessionIdRef.current?.value || "").trim();

    if (!currentUsername) {
      setMessage({ type: "error", text: "Please enter your Instagram username." });
      return;
    }
    if (!currentSessionId) {
      setMessage({ type: "error", text: "Please paste your Instagram sessionid cookie." });
      return;
    }

    setIsSubmitting(true);
    setMessage(null);

    try {
      const res = await api.settings.connectInstagramSession({
        username: currentUsername,
        session_id: currentSessionId,
      });

      if (res.success) {
        setMessage({
          type: "success",
          text: res.message || `Session cookie saved! Connected as @${currentUsername}.`,
        });
        setSessionId("");
        if (sessionIdRef.current) sessionIdRef.current.value = "";
        await loadStatus();
      } else {
        setMessage({
          type: "error",
          text: res.message || "Failed to save session cookie.",
        });
      }
    } catch (err: unknown) {
      const errDetail = err instanceof Error ? err.message : "Error connecting cookie";
      setMessage({ type: "error", text: errDetail });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRenew = async () => {
    setIsRenewing(true);
    setMessage(null);

    try {
      const res = await api.settings.renewInstagram();
      if (res.success) {
        setMessage({
          type: "success",
          text: res.message || "Session renewed successfully!",
        });
        await loadStatus();
      } else {
        setMessage({
          type: "error",
          text: res.message || "Auto-renewal failed. Please re-enter your password or cookie.",
        });
      }
    } catch (err: unknown) {
      const errDetail = err instanceof Error ? err.message : "Renewal failed";
      setMessage({ type: "error", text: errDetail });
    } finally {
      setIsRenewing(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect this Instagram account?")) return;
    try {
      await api.settings.disconnectInstagram();
      setUsername("");
      setPassword("");
      setSessionId("");
      setMessage({ type: "success", text: "Instagram account disconnected." });
      await loadStatus();
    } catch (err: unknown) {
      const errDetail = err instanceof Error ? err.message : "Error disconnecting account";
      setMessage({ type: "error", text: errDetail });
    }
  };

  const getStatusBadge = () => {
    if (!igStatus || !igStatus.configured) {
      return (
        <span
          style={{
            background: "rgba(107, 110, 116, 0.15)",
            color: "var(--ink-soft)",
            padding: "4px 10px",
            borderRadius: "12px",
            fontSize: "12px",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--ink-soft)" }} />
          Not Configured
        </span>
      );
    }

    if (igStatus.status === "connected" && igStatus.has_session) {
      return (
        <span
          style={{
            background: "rgba(34, 197, 94, 0.15)",
            color: "#22c55e",
            padding: "4px 10px",
            borderRadius: "12px",
            fontSize: "12px",
            fontWeight: 600,
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e" }} />
          Active & Ready
        </span>
      );
    }

    return (
      <span
        style={{
          background: "rgba(239, 68, 68, 0.15)",
          color: "#ef4444",
          padding: "4px 10px",
          borderRadius: "12px",
          fontSize: "12px",
          fontWeight: 600,
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#ef4444" }} />
        {igStatus.status.replace("_", " ").toUpperCase()}
      </span>
    );
  };

  return (
    <div style={{ maxWidth: 840, margin: "0 auto", paddingBottom: 60 }}>
      <h1 className="page-title">Settings</h1>
      <p className="page-sub">Configure Instagram scraping credentials, auto-renewal, and platform preferences.</p>

      {/* Instagram Scraping Credentials Card */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "6px",
          padding: "24px",
          marginBottom: "28px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.02)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: "17px", fontWeight: 600, margin: "0 0 4px" }}>
              Instagram Scraping Account
            </h2>
            <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
              The account used to query reels and competitor public metrics.
            </div>
          </div>
          <div>{getStatusBadge()}</div>
        </div>

        {/* Status detail box if configured */}
        {igStatus?.configured && (
          <div
            style={{
              background: "var(--bg)",
              border: "1px solid var(--line)",
              borderRadius: "4px",
              padding: "12px 16px",
              marginBottom: "20px",
              fontSize: "13px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <div>
              <span style={{ color: "var(--ink-soft)" }}>Connected Account: </span>
              <strong className="mono" style={{ color: "var(--ink)" }}>@{igStatus.username}</strong>
              {igStatus.last_authenticated && (
                <span style={{ marginLeft: 16, color: "var(--ink-soft)", fontSize: "12px" }}>
                  Last authenticated: {new Date(igStatus.last_authenticated).toLocaleString()}
                </span>
              )}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn"
                onClick={handleRenew}
                disabled={isRenewing}
                style={{ fontSize: "12px", padding: "6px 12px" }}
              >
                {isRenewing ? "Renewing..." : "🔄 Test / Renew Session"}
              </button>
              <button
                type="button"
                className="btn"
                onClick={handleDisconnect}
                style={{ fontSize: "12px", padding: "6px 12px", color: "#ef4444" }}
              >
                Disconnect
              </button>
            </div>
          </div>
        )}

        {igStatus?.error_message && (
          <div
            style={{
              background: "rgba(239, 68, 68, 0.08)",
              border: "1px solid rgba(239, 68, 68, 0.25)",
              color: "#ef4444",
              borderRadius: "4px",
              padding: "12px 16px",
              fontSize: "13px",
              marginBottom: "20px",
            }}
          >
            <strong>Session Notice:</strong> {igStatus.error_message}
          </div>
        )}

        {message && (
          <div
            style={{
              background: message.type === "success" ? "rgba(34, 197, 94, 0.08)" : "rgba(239, 68, 68, 0.08)",
              border: `1px solid ${message.type === "success" ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
              color: message.type === "success" ? "#16a34a" : "#ef4444",
              borderRadius: "4px",
              padding: "12px 16px",
              fontSize: "13px",
              marginBottom: "20px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{message.text}</span>
            <button
              type="button"
              onClick={() => setMessage(null)}
              style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", fontWeight: 700 }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Method selector tabs */}
        <div style={{ display: "flex", gap: 12, borderBottom: "1px solid var(--line)", marginBottom: 20 }}>
          <button
            type="button"
            onClick={() => setAuthMethod("password")}
            style={{
              padding: "8px 16px",
              background: "none",
              border: "none",
              borderBottom: authMethod === "password" ? "2px solid var(--accent)" : "2px solid transparent",
              color: authMethod === "password" ? "var(--ink)" : "var(--ink-soft)",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            🔑 Account Password (Auto-Renewing)
          </button>
          <button
            type="button"
            onClick={() => setAuthMethod("cookie")}
            style={{
              padding: "8px 16px",
              background: "none",
              border: "none",
              borderBottom: authMethod === "cookie" ? "2px solid var(--accent)" : "2px solid transparent",
              color: authMethod === "cookie" ? "var(--ink)" : "var(--ink-soft)",
              fontWeight: 600,
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            🍪 Session Cookie (Bypasses Checkpoint)
          </button>
        </div>

        {authMethod === "password" ? (
          /* Password Form */
          <form onSubmit={handleConnectPassword}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--ink-soft)", marginBottom: 6 }}>
                  Instagram Username
                </label>
                <div style={{ position: "relative" }}>
                  <span
                    style={{
                      position: "absolute",
                      left: 10,
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--ink-soft)",
                      fontSize: "14px",
                    }}
                  >
                    @
                  </span>
                  <input
                    ref={usernameRef}
                    type="text"
                    placeholder="username"
                    value={username.replace(/^@/, "")}
                    onChange={(e) => setUsername(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "9px 12px 9px 28px",
                      background: "var(--bg)",
                      border: "1px solid var(--line)",
                      borderRadius: "4px",
                      color: "var(--ink)",
                      fontSize: "13.5px",
                      fontFamily: "inherit",
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--ink-soft)", marginBottom: 6 }}>
                  Instagram Password
                </label>
                <div style={{ position: "relative" }}>
                  <input
                    ref={passwordRef}
                    type={showPassword ? "text" : "password"}
                    placeholder="account password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "9px 40px 9px 12px",
                      background: "var(--bg)",
                      border: "1px solid var(--line)",
                      borderRadius: "4px",
                      color: "var(--ink)",
                      fontSize: "13.5px",
                      fontFamily: "inherit",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: "absolute",
                      right: 8,
                      top: "50%",
                      transform: "translateY(-50%)",
                      background: "none",
                      border: "none",
                      color: "var(--ink-soft)",
                      fontSize: "12px",
                      padding: "4px",
                    }}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20 }}>
              <div style={{ fontSize: "12px", color: "var(--ink-soft)", maxWidth: "60%" }}>
                🔒 <strong>Auto-Renewal:</strong> When an Instagram session expires, Content Outlier automatically logs in again in the background and resumes scraping seamlessly.
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmitting}
                style={{
                  background: "var(--accent)",
                  color: "#fff",
                  border: "none",
                  padding: "10px 22px",
                  borderRadius: "4px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: isSubmitting ? "wait" : "pointer",
                  opacity: isSubmitting ? 0.7 : 1,
                }}
              >
                {isSubmitting ? "Connecting to Instagram..." : "Connect Account"}
              </button>
            </div>
          </form>
        ) : (
          /* Session Cookie Form */
          <form onSubmit={handleConnectCookie}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--ink-soft)", marginBottom: 6 }}>
                  Instagram Username
                </label>
                <div style={{ position: "relative" }}>
                  <span
                    style={{
                      position: "absolute",
                      left: 10,
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--ink-soft)",
                      fontSize: "14px",
                    }}
                  >
                    @
                  </span>
                  <input
                    ref={usernameRef}
                    type="text"
                    placeholder="username"
                    value={username.replace(/^@/, "")}
                    onChange={(e) => setUsername(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "9px 12px 9px 28px",
                      background: "var(--bg)",
                      border: "1px solid var(--line)",
                      borderRadius: "4px",
                      color: "var(--ink)",
                      fontSize: "13.5px",
                      fontFamily: "inherit",
                    }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--ink-soft)", marginBottom: 6 }}>
                  Instagram sessionid Cookie
                </label>
                <input
                  ref={sessionIdRef}
                  type="text"
                  placeholder="Paste your sessionid cookie here"
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "9px 12px",
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                    borderRadius: "4px",
                    color: "var(--ink)",
                    fontSize: "13.5px",
                    fontFamily: "inherit",
                  }}
                />
              </div>
            </div>

            <div style={{ fontSize: "12px", color: "var(--ink-soft)", marginBottom: 16 }}>
              💡 <strong>How to get your sessionid:</strong> Open instagram.com in Chrome/Edge &rarr; Press F12 (DevTools) &rarr; Go to Application tab &rarr; Cookies &rarr; https://www.instagram.com &rarr; copy the value of <code>sessionid</code>.
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmitting}
                style={{
                  background: "var(--accent)",
                  color: "#fff",
                  border: "none",
                  padding: "10px 22px",
                  borderRadius: "4px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: isSubmitting ? "wait" : "pointer",
                  opacity: isSubmitting ? 0.7 : 1,
                }}
              >
                {isSubmitting ? "Saving Session..." : "Connect Session Cookie"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* General Platform Settings */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "6px",
          padding: "24px",
          marginBottom: "28px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.02)",
        }}
      >
        <h2 style={{ fontSize: "17px", fontWeight: 600, margin: "0 0 16px" }}>
          Scraping Behavior
        </h2>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "14px 0",
            borderBottom: "1px solid var(--line)",
          }}
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "13.5px" }}>Scrape Trigger Mode</div>
            <div style={{ fontSize: "12.5px", color: "var(--ink-soft)", marginTop: 2 }}>
              Scrapes trigger automatically when you open the platform, with no background server cron jobs needed.
            </div>
          </div>
          <span
            style={{
              background: "rgba(31, 58, 95, 0.08)",
              color: "var(--accent)",
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "12px",
              fontWeight: 600,
            }}
          >
            On Platform Open
          </span>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "14px 0",
          }}
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "13.5px" }}>Automatically Download Outliers</div>
            <div style={{ fontSize: "12.5px", color: "var(--ink-soft)", marginTop: 2 }}>
              Download MP4 video files locally when an outlier is detected (multiplier &gt; 3x).
            </div>
          </div>
          <button
            className={`switch${autoDownload ? " on" : ""}`}
            onClick={() => setAutoDownload((v) => !v)}
            aria-label="Toggle auto-download"
          />
        </div>
      </div>
    </div>
  );
}
