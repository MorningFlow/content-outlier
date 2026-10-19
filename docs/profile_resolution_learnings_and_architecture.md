# Architectural Learnings: Instagram Profile Resolution & Scraping Resilience

This document outlines key technical insights derived from reverse-engineering [imginn.com](https://imginn.com) and Meta's current anti-scraping perimeter, detailing how to eliminate profile lookup failures and silent scrape aborts in Content Outlier.

---

## 1. The Core Bottleneck: Username vs. Numeric User ID

Instagram's modern infrastructure does not index content by username. Usernames are mutable strings, whereas all internal feeds, graph nodes, and clips connections require an immutable 64-bit numeric identifier (`target_user_id` / `pk`).

In Content Outlier, [app/scraper/collector.py](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/app/scraper/collector.py) previously attempted an all-or-nothing pipeline:
1. Hit `web_profile_info` by username &rarr; Blocked with HTTP 429.
2. Fall back to `imginn.com/<username>/` via `httpx` &rarr; Blocked with Cloudflare HTTP 403.
3. Fail silently, return `instagram_id = None`, and complete the job with zero tracked posts.

By contrast, Imginn treats the username solely as an alias to resolve the numeric ID (`59161778770` for `@nivedan.ai`). Once that ID is resolved, all subsequent calls target Instagram's clips and media endpoints directly using numeric IDs.

---

## 2. The "Shortcode Anchor" Discovery Technique

While Meta aggressively shields profile lookup endpoints (`web_profile_info`) behind authentication challenges, individual Reels and post URLs (`https://www.instagram.com/reel/<shortcode>/`) remain **completely open and unauthenticated**.

Every public post payload returned by Instagram includes the full author metadata block:
```json
{
  "owner": {
    "id": "59161778770",
    "username": "nivedan.ai",
    "full_name": "Nivedan Rathi"
  }
}
```

### Strategic Application
If the platform knows or can discover even **a single Reel shortcode** for an account, it can resolve the numeric ID, verified full name, and avatar without an Instagram session and without hitting blocked profile endpoints.

Shortcodes can be discovered through:
1. Search engine indices (`site:instagram.com/reel/ "nivedan.ai"`).
2. Allowing users to paste any sample Reel URL when adding a competitor.
3. Mirror indexing pipelines.

---

## 3. Cloudflare Mitigation & TLS Fingerprinting

When testing in a live browser, `imginn.com/nivedan.ai/` rendered immediately without human interaction. However, Python HTTP clients (`requests`, `httpx`, `curl`) received `HTTP 403 Forbidden` (`Cf-Mitigated: challenge`).

Cloudflare inspects low-level TLS handshakes:
- **JA3/JA4 Fingerprints**: Standard Python libraries use default OpenSSL cipher suites, which Cloudflare identifies as non-browser traffic.
- **Client Hints & Protocol**: HTTP/1.1 requests missing `Sec-Ch-Ua`, `Sec-Fetch-Mode`, and `Sec-Fetch-Dest` headers are dropped before reaching origin servers.

### Strategic Application
When scraping third-party mirrors or web platforms:
1. Never rely on raw `httpx` or `requests` for Cloudflare-protected endpoints.
2. Use TLS-impersonating engines (`curl_cffi` with browser fingerprint emulation) or lightweight headless browser sessions.
3. Prioritize authenticated local residential sessions over public mirrors, eliminating third-party Cloudflare dependencies entirely.

---

## 4. Media Hotlink Prevention

Instagram sets strict `Cross-Origin-Resource-Policy` headers and validates referrer origins on image CDN requests (`scontent.cdninstagram.com`). Hotlinking thumbnails directly in an external dashboard results in broken images.

Imginn solves this by routing image traffic through sharded edge proxies (`s1.imginn.com` - `s11.imginn.com`) that fetch the image with spoofed Instagram headers, strip referrer checks, and serve the cached binary asset.

### Strategic Application
Content Outlier's architecture of saving profile pictures and video thumbnails to local disk ([media_storage/](file:///c:/Users/Unleashed/Desktop/Work/MyTASKengine/ContentOutlier/media_storage)) is the correct long-term strategy. To prevent broken avatars, the collector should pull the avatar directly upon resolving the first valid post node.

---

## 5. Resilient Multi-Tier Resolution Pipeline

To guarantee that adding competitors never fails silently, Content Outlier implements a four-tier resolution fallback:

```
[Add Competitor: @username or Reel URL]
               │
               ▼
[Tier 1: Authenticated Session]
  - Query Instagram search API (/web/search/topsearch/)
  - Fetch full GraphQL clips connection
               │ (if unauthenticated or failed)
               ▼
[Tier 2: Shortcode Extraction / Seed Post]
  - Extract shortcode from input or search engine index
  - Parse owner.id, full_name, and avatar from Post node
               │ (if shortcode found)
               ▼
[Tier 3: Browser / TLS-Impersonated Mirror]
  - Query mirror using full browser TLS profile
               │ (if all fail)
               ▼
[Tier 4: Actionable State Feedback]
  - Mark competitor status as 'needs_auth'
  - Display alert in UI directing user to Settings to link Instagram
  - Never mark empty jobs as 'completed'
```
