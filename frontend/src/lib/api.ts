// ── API client ────────────────────────────────────────────────────────────────
// All calls go through here. Set NEXT_PUBLIC_API_URL in .env.local to point
// at your FastAPI server (e.g. https://api.yourdomain.com).
// Media paths returned by the API are root-relative (/media/...) and must be
// resolved against the API origin — resolveMedia() handles that.

function getBaseUrl(): string {
  if (typeof window !== "undefined") {
    // In browser: use /api rewrite proxy unless an external URL is explicitly provided
    const pub = process.env.NEXT_PUBLIC_API_URL;
    if (pub && pub.startsWith("http") && !pub.includes("localhost") && !pub.includes("127.0.0.1")) {
      return pub.replace(/\/$/, "");
    }
    return "/api";
  }
  // In server-side rendering (Node.js runtime on VPS): reach FastAPI directly on localhost
  const serverBase = process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000";
  return serverBase.replace(/\/$/, "");
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const base = getBaseUrl();
  let normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (base === "/api" && normalizedPath.startsWith("/api/")) {
    normalizedPath = normalizedPath.slice(4);
  }
  const url = `${base}${normalizedPath}`;
  try {
    return await fetch(url, init);
  } catch (err: unknown) {
    if (err instanceof TypeError) {
      throw new Error(`Cannot connect to backend API at ${url}. Ensure the FastAPI server is running.`);
    }
    throw err;
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await request(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `POST ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await request(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
}

/** Resolve a root-relative media path returned by FastAPI to an absolute or relative URL. */
export function resolveMedia(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const pub = process.env.NEXT_PUBLIC_API_URL;
  if (pub && pub.startsWith("http") && !pub.includes("localhost") && !pub.includes("127.0.0.1")) {
    return `${pub.replace(/\/$/, "")}${cleanPath}`;
  }
  return cleanPath;
}

// ── Types (mirrors Pydantic schemas) ─────────────────────────────────────────

export interface DashboardData {
  competitors_count: number;
  content_tracked_count: number;
  outliers_found_count: number;
  last_updated_human: string;
  top_outlier: OutlierCard | null;
}

export interface JobRecord {
  id: string;
  job_type: string;
  status: string; // queued, running, completed, failed
  competitor_id?: string | null;
  content_id?: string | null;
  attempts: number;
  max_attempts: number;
  progress_percent: number;
  progress_stage?: string | null;
  error_message?: string | null;
  scheduled_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface AddCompetitorResponse {
  competitor: CompetitorRecord;
  job: JobRecord;
  message: string;
}

export interface CompetitorRecord {
  id: string;
  username: string;
  display_name: string | null;
  profile_name?: string | null;
  profile_image?: string | null;
  follower_count: number | null;
  followers?: number | null;
  content_count: number;
  last_scraped_at: string | null;
  is_active: boolean;
  status?: string;
  scrape_error?: string | null;
  instagram_id?: string | null;
  created_at: string;
  active_job?: JobRecord | null;
}

export interface OutlierCard {
  id: string;
  shortcode: string;
  instagram_url: string;
  username: string;
  caption: string | null;
  thumbnail_url: string | null;
  video_url: string | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  published_at: string;
  age_days: number;
  outlier_score: number;
  view_multiplier: number | null;
  baseline_views: number | null;
  engagement_rate: number | null;
  view_velocity: number | null;
  outlier_reasons: Record<string, unknown> | null;
  download_status: string;
  transcription_status: string;
}

export interface OutlierListResponse {
  items: OutlierCard[];
  total: number;
  page: number;
  limit: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptResponse {
  id: string;
  content_id: string;
  full_text: string;
  language?: string;
  duration?: number | null;
  segments: TranscriptSegment[] | null;
  hook_text?: string | null;
  breakdown_hook: string | null;
  breakdown_topic: string | null;
  breakdown_format: string | null;
  breakdown_cta: string | null;
  key_takeaways: string | null;
  created_at: string;
}

export interface ContentItem {
  id: string;
  competitor_id: string;
  instagram_username: string;
  shortcode: string;
  instagram_url: string;
  content_type: string;
  published_at: string;
  caption: string | null;
  thumbnail_url: string | null;
  video_url: string | null;
  video_path: string | null;
  video_duration: number | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  share_count: number | null;
  save_count: number | null;
  is_outlier: boolean;
  outlier_score: number;
  view_multiplier: number | null;
  engagement_rate: number | null;
  view_velocity: number | null;
  outlier_reasons: Record<string, unknown> | null;
  download_status: string;
  transcription_status: string;
  first_discovered_at: string;
  last_scraped_at: string;
  created_at: string;
  updated_at: string;
}

export interface ContentDetailItem extends ContentItem {
  metrics: unknown[];
  transcript: TranscriptResponse | null;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const api = {
  dashboard: () => get<DashboardData>("/dashboard"),

  competitors: {
    list: () => get<CompetitorRecord[]>("/competitors"),
    add: (username: string) => post<AddCompetitorResponse>("/competitors", { username }),
    delete: (id: string) => del(`/competitors/${id}`),
    sync: (id: string) => post<JobRecord>(`/competitors/${id}/sync`),
    /** Queues incremental syncs for all active competitors — called on platform open. */
    syncAll: () => post<{ queued: string[]; skipped: string[]; message: string }>("/competitors/sync-all"),
  },

  jobs: {
    get: (id: string) => get<JobRecord>(`/jobs/${id}`),
  },

  outliers: (params: {
    competitor?: string;
    range?: string;
    sort?: string;
    page?: number;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.competitor) q.set("competitor", params.competitor);
    if (params.range) q.set("range", params.range);
    if (params.sort) q.set("sort", params.sort);
    q.set("page", String(params.page ?? 1));
    q.set("limit", String(params.limit ?? 20));
    return get<OutlierListResponse>(`/outliers?${q}`);
  },

  content: {
    list: (params: {
      competitor?: string;
      range?: string;
      sort?: string;
      order?: string;
      search?: string;
      page?: number;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      if (params.competitor) q.set("competitor", params.competitor);
      if (params.range) q.set("range", params.range);
      if (params.sort) q.set("sort", params.sort);
      if (params.order) q.set("order", params.order);
      if (params.search) q.set("search", params.search);
      q.set("page", String(params.page ?? 1));
      q.set("limit", String(params.limit ?? 50));
      return get<ContentItem[]>(`/content?${q}`);
    },
    get: (id: string) => get<ContentDetailItem>(`/content/${id}`),
    requestDownload: (id: string) => post<unknown>(`/content/${id}/download`),
    transcribe: (id: string) => post<TranscriptResponse>(`/content/${id}/transcribe`),
  },

  settings: {
    getInstagram: () =>
      get<{
        configured: boolean;
        username: string | null;
        status: string;
        has_session: boolean;
        last_authenticated: string | null;
        error_message: string | null;
      }>("/settings/instagram"),
    connectInstagram: (data: { username: string; password: string }) =>
      post<{
        success: boolean;
        message: string;
        status: string;
        username?: string | null;
      }>("/settings/instagram", data),
    connectInstagramSession: (data: { username: string; session_id: string; ds_user_id?: string }) =>
      post<{
        success: boolean;
        message: string;
        status: string;
        username?: string | null;
      }>("/settings/instagram/session", data),

    renewInstagram: () =>
      post<{
        success: boolean;
        message: string;
        status: string;
        username?: string | null;
      }>("/settings/instagram/renew"),
    disconnectInstagram: () => del("/settings/instagram"),
  },
};

