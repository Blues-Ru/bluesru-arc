/**
 * Blues.Ru media middleware for Cloudflare Pages.
 *
 * Intercepts requests for media files (images, audio, etc.) and serves them
 * from Cloudflare R2 via the internal-media.blues.ru origin.
 *
 * Invariant: the R2 key for any media URL is deterministic:
 *   URL path  →  R2 key = "bluesru-media" + URL path
 *
 * Exceptions (URL dir prefix → R2 dir prefix):
 *   /atb/excerpts/              → excerpts/
 *   /atb/kalachev-kostin-show/  → kalachev-kostin-show/
 *
 * Non-media requests (HTML, CSS, JS) pass through to CF Pages static assets.
 */

// R2 origin — internal hostname mapped to the R2 bucket
const R2_ORIGIN = "https://internal-media.blues.ru";
const R2_PREFIX = "bluesru-media";
const R2_CACHE_PREFIX = "bluesru-media.cache";

// Media file extensions served from R2
const MEDIA_EXTENSIONS = new Set([
  ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
  ".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm",
  ".ra", ".rm", ".pdf",
]);

// Custom URL prefix → R2 path prefix remaps.
// Key: URL path prefix (with trailing slash), Value: R2 subpath (no leading slash)
// These override the default 1:1 mapping for directories whose names differ between URL and R2.
const CUSTOM_DIR_PREFIXES = [
  ["/atb/excerpts/", "excerpts/"],
  ["/atb/kalachev-kostin-show/", "kalachev-kostin-show/"],
];

/**
 * Resolve a URL path to its R2 fetch URL.
 * Returns null if the path is not a media file.
 */
function resolveMediaUrl(pathname) {
  // Only handle known media extensions
  const dot = pathname.lastIndexOf(".");
  if (dot < 0) return null;
  const ext = pathname.slice(dot).toLowerCase();
  if (!MEDIA_EXTENSIONS.has(ext)) return null;

  // Apply custom directory prefix overrides first
  for (const [urlPrefix, r2dir] of CUSTOM_DIR_PREFIXES) {
    if (pathname.startsWith(urlPrefix)) {
      const rest = pathname.slice(urlPrefix.length);
      return `${R2_ORIGIN}/${R2_PREFIX}/${r2dir}${rest}`;
    }
  }

  // Thumbnails: *-400w.jpg served from cache prefix
  if (pathname.endsWith("-400w.jpg")) {
    return `${R2_ORIGIN}/${R2_CACHE_PREFIX}${pathname}`;
  }

  // Default 1:1 mapping: URL path maps to R2 key = R2_PREFIX + pathname
  return `${R2_ORIGIN}/${R2_PREFIX}${pathname}`;
}

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const mediaUrl = resolveMediaUrl(url.pathname);

  if (mediaUrl) {
    // Fetch from R2 origin
    const r2Response = await fetch(mediaUrl, {
      // Forward range requests for audio seeking
      headers: {
        ...(request.headers.get("Range")
          ? { Range: request.headers.get("Range") }
          : {}),
        ...(request.headers.get("If-None-Match")
          ? { "If-None-Match": request.headers.get("If-None-Match") }
          : {}),
        ...(request.headers.get("If-Modified-Since")
          ? { "If-Modified-Since": request.headers.get("If-Modified-Since") }
          : {}),
      },
    });

    if (r2Response.status !== 404) {
      // Return R2 response with CORS headers
      const headers = new Headers(r2Response.headers);
      headers.set("Access-Control-Allow-Origin", "*");
      headers.set("Cache-Control", "public, max-age=86400");
      return new Response(r2Response.body, {
        status: r2Response.status,
        headers,
      });
    }
    // 404 from R2: fall through to Pages static assets (may also 404, that's OK)
  }

  // Non-media request or R2 miss: serve from CF Pages static site
  return context.next();
}
