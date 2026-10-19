"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { api, ContentItem, CompetitorRecord } from "@/lib/api";
import { fmt, relAge } from "@/lib/format";
import { resolveMedia } from "@/lib/api";

const LIB_LIMIT = 50;

export default function LibraryPage() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [competitors, setCompetitors] = useState<CompetitorRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [competitor, setCompetitor] = useState("");
  const [range, setRange] = useState("90d");
  const [sort, setSort] = useState("published");
  const [page, setPage] = useState(1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.competitors.list().then(setCompetitors).catch(console.error);
  }, []);

  const load = useCallback((pg: number) => {
    setLoading(true);
    api.content
      .list({
        competitor: competitor || undefined,
        range,
        sort,
        order: "desc",
        search: search.trim() || undefined,
        page: pg,
        limit: LIB_LIMIT,
      })
      .then(setItems)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [competitor, range, sort, search]);

  useEffect(() => { setPage(1); load(1); }, [competitor, range, sort]);

  // Debounce search input
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setPage(1); load(1); }, 320);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  function goPage(p: number) {
    setPage(p);
    load(p);
  }

  return (
    <>
      <h1 className="page-title">Content Library</h1>
      <p className="page-sub">
        Every tracked competitor Reel — searchable, filterable, and sorted across 30, 60, and 90‑day horizons.
      </p>

      <div className="section-head" style={{ marginBottom: 12 }}>
        <div className="toolbar" style={{ flexWrap: "wrap", gap: 8, width: "100%" }}>
          <input
            className="search"
            type="search"
            placeholder="Search captions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: 180, maxWidth: 320 }}
          />
          <select value={competitor} onChange={(e) => setCompetitor(e.target.value)}>
            <option value="">All Competitors</option>
            {competitors.map((c) => (
              <option key={c.id} value={c.username}>@{c.username}</option>
            ))}
          </select>
          <select value={range} onChange={(e) => setRange(e.target.value)}>
            <option value="30d">Last 30 Days</option>
            <option value="60d">Last 60 Days</option>
            <option value="90d">Last 90 Days</option>
            <option value="all">All Time</option>
          </select>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="published">Newest First</option>
            <option value="views">Most Views</option>
            <option value="score">Outlier Score</option>
            <option value="likes">Most Likes</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="stub">Loading…</div>
      ) : items.length === 0 ? (
        <div className="stub">No content found for the selected filters.</div>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 44, paddingLeft: 14 }} />
                  <th style={{ minWidth: 140 }}>Account</th>
                  <th style={{ minWidth: 150 }}>Caption</th>
                  <th style={{ width: 80, whiteSpace: "nowrap" }}>Age</th>
                  <th className="mono" style={{ textAlign: "right", width: 75, whiteSpace: "nowrap" }}>Views</th>
                  <th className="mono" style={{ textAlign: "right", width: 70, whiteSpace: "nowrap" }}>Likes</th>
                  <th className="mono" style={{ textAlign: "right", width: 80, whiteSpace: "nowrap" }}>Comments</th>
                  <th style={{ textAlign: "center", width: 65, whiteSpace: "nowrap" }}>Score</th>
                  <th style={{ textAlign: "right", paddingRight: 16, width: 175, whiteSpace: "nowrap" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const isOutlier = item.outlier_score >= 3.0;
                  const thumb = resolveMedia(item.thumbnail_url);
                  const caption = item.caption
                    ? item.caption.length > 70
                      ? item.caption.slice(0, 70) + "…"
                      : item.caption
                    : null;

                  return (
                    <tr key={item.id}>
                      <td style={{ paddingLeft: 14 }}>
                        <Link href={`/analysis/${item.id}`}>
                          <div
                            className="lib-thumb"
                            style={
                              thumb
                                ? { backgroundImage: `url(${thumb})`, backgroundSize: "cover", backgroundPosition: "center" }
                                : undefined
                            }
                          >
                            <span className="lib-play-icon">▶</span>
                          </div>
                        </Link>
                      </td>
                      <td>
                        <div className="row-user" style={{ display: "flex", alignItems: "center" }}>
                          <img
                            src={resolveMedia(`/media/profiles/${item.instagram_username}.jpg`)!}
                            onError={(e) => { (e.target as HTMLElement).style.display = "none"; }}
                            alt={item.instagram_username}
                            style={{ width: 22, height: 22, borderRadius: "50%", marginRight: 7, objectFit: "cover" }}
                          />
                          <span style={{ fontSize: 12.5, fontWeight: 600 }}>@{item.instagram_username}</span>
                        </div>
                      </td>
                      <td>
                        {caption ? (
                          <Link
                            href={`/analysis/${item.id}`}
                            style={{ fontSize: 12.5, lineHeight: 1.4, color: "var(--ink)", maxWidth: 280, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                            title={item.caption ?? ""}
                          >
                            {caption}
                          </Link>
                        ) : (
                          <span style={{ color: "var(--ink-soft)", fontSize: 12 }}>—</span>
                        )}
                      </td>
                      <td className="mono" style={{ fontSize: 12, whiteSpace: "nowrap", color: "var(--ink-soft)" }}>
                        {relAge(item.published_at)}
                      </td>
                      <td className="mono" style={{ fontSize: 12, textAlign: "right", whiteSpace: "nowrap" }}>
                        {fmt(item.view_count)}
                      </td>
                      <td className="mono" style={{ fontSize: 12, textAlign: "right", whiteSpace: "nowrap" }}>
                        {fmt(item.like_count)}
                      </td>
                      <td className="mono" style={{ fontSize: 12, textAlign: "right", whiteSpace: "nowrap" }}>
                        {fmt(item.comment_count)}
                      </td>
                      <td style={{ textAlign: "center", whiteSpace: "nowrap" }}>
                        {isOutlier ? (
                          <span className="badge-outlier-sm">{item.outlier_score}×</span>
                        ) : (
                          <span className="badge-baseline-sm">{item.outlier_score}×</span>
                        )}
                      </td>
                      <td style={{ textAlign: "right", paddingRight: 16, whiteSpace: "nowrap" }}>
                        <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "flex-end", gap: 12 }}>
                          <Link
                            href={`/analysis/${item.id}`}
                            style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", textDecoration: "none" }}
                          >
                            View Analysis →
                          </Link>
                          <a
                            href={item.instagram_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: 11.5, color: "var(--ink-soft)", textDecoration: "none" }}
                          >
                            Instagram ↗
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14, fontSize: 12.5, color: "var(--ink-soft)" }}>
            {page > 1 && (
              <button className="btn" onClick={() => goPage(page - 1)}>← Prev</button>
            )}
            <span>Page {page} · {items.length} items</span>
            {items.length === LIB_LIMIT && (
              <button className="btn" onClick={() => goPage(page + 1)}>Next →</button>
            )}
          </div>
        </>
      )}
    </>
  );
}
