import { api } from "@/lib/api";
import { fmt } from "@/lib/format";
import { resolveMedia } from "@/lib/api";
import Link from "next/link";

export default async function OverviewPage() {
  let data = null;
  try {
    data = await api.dashboard();
  } catch {
    // backend offline — render with nulls
  }

  const top = data?.top_outlier;

  return (
    <>
      <h1 className="page-title">Content Overview</h1>
      <p className="page-sub">
        Monitor competitor content and identify posts performing significantly above their normal baseline.
      </p>

      {/* Metrics Row */}
      <div className="metrics-row">
        <div className="metric">
          <div className="label">Competitors</div>
          <div className="value mono">{data?.competitors_count ?? "—"}</div>
        </div>
        <div className="metric">
          <div className="label">Content Tracked</div>
          <div className="value mono">{fmt(data?.content_tracked_count ?? null)}</div>
        </div>
        <div className="metric">
          <div className="label">Outliers Found</div>
          <div className="value mono">{data?.outliers_found_count ?? "—"}</div>
        </div>
        <div className="metric">
          <div className="label">Last Updated</div>
          <div className="value mono" style={{ fontSize: 18 }}>
            {data?.last_updated_human ?? "—"}
          </div>
        </div>
      </div>

      {/* Top Outlier */}
      <div className="section-head">
        <h2>Top Outliers</h2>
      </div>

      {top ? (
        <div className="hero-outlier">
          <div
            className="thumb"
            style={
              top.thumbnail_url
                ? {
                    backgroundImage: `url(${resolveMedia(top.thumbnail_url)})`,
                    backgroundSize: "cover",
                    backgroundPosition: "center",
                  }
                : undefined
            }
          >
            <span className="badge">{top.outlier_score}× OUTLIER</span>
          </div>
          <div className="hero-body">
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5, fontWeight: 600 }}>
              <img
                src={resolveMedia(`/media/profiles/${top.username}.jpg`)!}
                alt={top.username}
                style={{ width: 22, height: 22, borderRadius: "50%", objectFit: "cover" }}
              />
              <span>@{top.username}</span>
            </div>
            <div style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 13, color: "var(--ink-soft)" }}>
              {fmt(top.view_count)} views · {fmt(top.like_count)} likes · {fmt(top.comment_count)} comments
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>Posted {top.age_days} days ago</div>
            <Link className="card-link" href={`/analysis/${top.id}`}>
              View Analysis →
            </Link>
          </div>
        </div>
      ) : (
        <div className="stub">No outlier data yet — add a competitor to start tracking.</div>
      )}
    </>
  );
}
