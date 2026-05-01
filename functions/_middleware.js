/**
 * Blues.Ru middleware for Cloudflare Pages.
 *
 * Handles two responsibilities:
 *
 * 1. Redirect legacy URLs:
 *    - /data/albumview.aspx?cdid=N  → /artist/{artist}/{album}/
 *    - /data/artistview.aspx?aid=N  → /artist/{slug}/
 *    - /news.aspx?y=YYYY            → /updates/YYYY/
 *    - /bluesmen/OldDir/...         → /artist/slug/...
 *    - /bluesnews/_NN/subdir/...    → /photo/YYYY/slug/
 *    Redirect data loaded from /data/redirects.json (generated during build).
 *
 * 2. Serve media from R2:
 *    Requests for media files (images, audio, etc.) are proxied to the R2
 *    bucket via internal-media.blues.ru. Non-media falls through to CF Pages
 *    static assets.
 *
 * R2 key for any media URL:  "bluesru-media" + URL path  (1:1, with exceptions)
 */

// ── R2 config ─────────────────────────────────────────────────────────────────
const R2_ORIGIN = "https://internal-media.blues.ru";
const R2_PREFIX = "bluesru-media";
const R2_CACHE_PREFIX = "bluesru-media.cache";

const MEDIA_EXTENSIONS = new Set([
  ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
  ".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".webm",
  ".ra", ".rm", ".pdf",
]);

const CUSTOM_DIR_PREFIXES = [
  ["/atb/excerpts/", "excerpts/"],
  ["/atb/kalachev-kostin-show/", "kalachev-kostin-show/"],
];

function resolveMediaUrl(pathname) {
  const dot = pathname.lastIndexOf(".");
  if (dot < 0) return null;
  const ext = pathname.slice(dot).toLowerCase();
  if (!MEDIA_EXTENSIONS.has(ext)) return null;

  for (const [urlPrefix, r2dir] of CUSTOM_DIR_PREFIXES) {
    if (pathname.startsWith(urlPrefix)) {
      const rest = pathname.slice(urlPrefix.length);
      return `${R2_ORIGIN}/${R2_PREFIX}/${r2dir}${rest}`;
    }
  }

  if (pathname.endsWith("-400w.jpg")) {
    return `${R2_ORIGIN}/${R2_CACHE_PREFIX}${pathname}`;
  }

  return `${R2_ORIGIN}/${R2_PREFIX}${pathname}`;
}

// ── Redirect manifest (loaded once per worker instance) ───────────────────────
let redirectManifest = null;

async function getManifest(env, requestUrl) {
  if (redirectManifest) return redirectManifest;
  try {
    const url = new URL("/data/redirects.json", requestUrl);
    const resp = await env.ASSETS.fetch(url.toString());
    if (resp.ok) {
      redirectManifest = await resp.json();
    }
  } catch (_) {}
  if (!redirectManifest) {
    redirectManifest = { albums: {}, artists: {}, bluesmen: {}, bluesnews: {} };
  }
  return redirectManifest;
}

function redirect301(target, requestUrl) {
  const dest = new URL(target, requestUrl).toString();
  return Response.redirect(dest, 301);
}

// ── Main handler ──────────────────────────────────────────────────────────────
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const { pathname, searchParams } = url;

  // ── Legacy aspx redirects (query-string based) ────────────────────────────
  if (pathname === "/data/albumview.aspx" || pathname === "/albumview.aspx") {
    const cdid = searchParams.get("cdid");
    if (cdid) {
      const m = await getManifest(env, request.url);
      const target = m.albums && m.albums[cdid];
      if (target) return redirect301(target, request.url);
    }
    return redirect301("/review/", request.url);
  }

  if (pathname === "/data/artistview.aspx" || pathname === "/artistview.aspx") {
    const aid = searchParams.get("aid");
    if (aid) {
      const m = await getManifest(env, request.url);
      const target = m.artists && m.artists[aid];
      if (target) return redirect301(target, request.url);
    }
    return redirect301("/artist/", request.url);
  }

  if (pathname === "/news.aspx") {
    const y = searchParams.get("y");
    if (y) return redirect301(`/updates/${y}/`, request.url);
    return redirect301("/updates/", request.url);
  }

  // ── Legacy /bluesmen/ directory redirects ─────────────────────────────────
  if (pathname.startsWith("/bluesmen/")) {
    const m = await getManifest(env, request.url);
    if (m.bluesmen) {
      // Extract the second path segment: /bluesmen/{dir}/...
      const rest = pathname.slice("/bluesmen/".length);
      const slash = rest.indexOf("/");
      const dir = slash >= 0 ? rest.slice(0, slash) : rest;
      const suffix = slash >= 0 ? rest.slice(slash) : "/";
      const target = m.bluesmen[dir];
      if (target) {
        return redirect301(target + (suffix === "/" ? "/" : suffix), request.url);
      }
    }
    // Fallback: pass-through to _redirects catch-all /bluesmen/* → /artist/:splat
  }

  // ── Legacy /bluesnews/ photo-gallery redirects ────────────────────────────
  if (pathname.startsWith("/bluesnews/")) {
    const m = await getManifest(env, request.url);
    if (m.bluesnews) {
      // Match longest prefix in bluesnews map
      for (const [fromPath, toPath] of Object.entries(m.bluesnews)) {
        if (pathname === fromPath || pathname.startsWith(fromPath + "/")) {
          return redirect301(toPath, request.url);
        }
      }
    }
    // Not a known gallery subdir — fall through to static assets (index pages etc.)
  }

  // ── Media from R2 ─────────────────────────────────────────────────────────
  const mediaUrl = resolveMediaUrl(pathname);
  if (mediaUrl) {
    const r2Response = await fetch(mediaUrl, {
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
      const headers = new Headers(r2Response.headers);
      headers.set("Access-Control-Allow-Origin", "*");
      headers.set("Cache-Control", "public, max-age=86400");
      return new Response(r2Response.body, {
        status: r2Response.status,
        headers,
      });
    }
  }

  return context.next();
}
