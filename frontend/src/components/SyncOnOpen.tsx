"use client";

/**
 * SyncOnOpen — fires once per browser session when the platform is opened.
 *
 * Strategy:
 *  1. Try the local scraping agent at http://localhost:9191/scrape
 *     (runs on your residential machine → Instagram never blocks it)
 *  2. If the agent isn't running, fall back to the VPS sync-all
 *     (may still fail due to datacenter IP blocks, but at least tries)
 *
 * Uses sessionStorage so a single browser session only triggers one scrape.
 */
import { useEffect } from "react";
import { api } from "@/lib/api";

const LOCAL_AGENT = "http://localhost:9191";

export default function SyncOnOpen() {
  useEffect(() => {
    const key = "contentoutlier_sync_fired";
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, "1");

    (async () => {
      // 1. Try local agent first
      try {
        const res = await fetch(`${LOCAL_AGENT}/scrape`, {
          method: "POST",
          signal: AbortSignal.timeout(3000), // fail fast if agent not running
        });
        if (res.ok) {
          console.info("[ContentOutlier] Local agent triggered — scraping from your residential IP.");
          return; // agent is handling it, done
        }
      } catch {
        // Agent not running — fall through to VPS
        console.info("[ContentOutlier] Local agent not detected — falling back to VPS sync.");
      }

      // 2. VPS fallback
      try {
        const res = await api.competitors.syncAll();
        if (res.queued.length > 0) {
          console.info(`[ContentOutlier] VPS sync queued for: ${res.queued.join(", ")}`);
        }
      } catch (err) {
        console.warn("[ContentOutlier] Sync-on-open fallback also failed:", err);
      }
    })();
  }, []);

  return null;
}
