"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { api, OutlierCard, CompetitorRecord } from "@/lib/api";
import { fmt, relAge } from "@/lib/format";
import { resolveMedia } from "@/lib/api";

export default function OutliersPage() {
  const [outliers, setOutliers] = useState<OutlierCard[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorRecord[]>([]);
  const [competitor, setCompetitor] = useState("");
  const [range, setRange] = useState("30d");
  const [sort, setSort] = useState("score");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.competitors.list().then(setCompetitors).catch(console.error);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    api
      .outliers({ competitor: competitor || undefined, range, sort })
      .then((r) => setOutliers(r.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [competitor, range, sort]);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <h1 className="page-title">Outliers</h1>
      <p className="page-sub">
        Content performing well beyond its account&apos;s normal baseline, ranked by outlier score.
      </p>

      <div className="section-head">
        <div className="toolbar">
          <select value={competitor} onChange={(e) => setCompetitor(e.target.value)}>
            <option value="">All Competitors</option>
            {competitors.map((c) => (
              <option key={c.id} value={c.username}>@{c.username}</option>
            ))}
          </select>
          <select value={range} onChange={(e) => setRange(e.target.value)}>
            <option value="30d">Last 30 days</option>
            <option value="7d">Last 7 days</option>
            <option value="90d">Last 90 days</option>
            <option value="all">All time</option>
          </select>
        </div>
        <div className="toolbar">
          <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>Sort by</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="score">Outlier Score</option>
            <option value="views">Views</option>
            <option value="velocity">Velocity</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="stub">Loading outliers…</div>
      ) : outliers.length === 0 ? (
        <div className="stub">No outliers found for the selected filter criteria.</div>
      ) : (
        <div className="outlier-grid">
          {outliers.map((o) => {
            const thumb = resolveMedia(o.thumbnail_url);
            return (
              <article className="outlier-card" key={o.id}>
                <Link
                  href={`/analysis/${o.id}`}
                  className="thumb"
                  style={thumb ? { backgroundImage: `url(${thumb})`, backgroundSize: "cover" } : undefined}
                >
                  <span className="badge">{o.outlier_score}× OUTLIER</span>
                  <span className="thumb-age">{o.age_days}d ago</span>
                </Link>
                <div className="card-body">
                  <div className="card-account">
                    <img
                      src={resolveMedia(`/media/profiles/${o.username}.jpg`)!}
                      onError={(e) => { (e.target as HTMLElement).style.display = "none"; }}
                      alt={o.username}
                      className="card-avatar"
                    />
                    <span className="card-username" title={`@${o.username}`}>@{o.username}</span>
                  </div>
                  <div className="card-metrics-block">
                    <div className="card-metric-primary">
                      <span className="val">{fmt(o.view_count)}</span>
                      <span className="lbl">views</span>
                    </div>
                    <div className="card-metric-secondary">
                      <span className="val">{fmt(o.like_count)}</span>
                      <span className="lbl">likes</span>
                    </div>
                  </div>
                  <div className="card-baseline-row">
                    <span className="baseline-lbl">Baseline</span>
                    <span className="baseline-val">{fmt(o.baseline_views)} avg</span>
                  </div>
                  <Link className="card-action-btn" href={`/analysis/${o.id}`}>
                    Analyze Reel →
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
