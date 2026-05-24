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
 *    Requests for media files are proxied to the R2 bucket via
 *    internal-media.blues.ru. Routing is extension-aware per URL prefix:
 *    only extensions actually present in R2 for that prefix go to R2;
 *    other extensions fall through to CF Pages static assets.
 *
 * R2 key for any media URL:  "bluesru-media" + URL path  (1:1, with exceptions)
 */

// ── R2 config ─────────────────────────────────────────────────────────────────
const R2_ORIGIN = "https://internal-media.blues.ru";
const R2_PREFIX = "bluesru-media";
const R2_CACHE_PREFIX = "bluesru-media.cache";

// Per-prefix map of extensions that exist in R2 (derived from actual R2 contents).
// If a URL's prefix is not listed here, it goes to context.next() (Pages assets).
// If the prefix is listed but the extension is not in its set, same: Pages assets.
// Thumbnails (-400w.jpg) under /photo/ use R2_CACHE_PREFIX regardless.
const R2_ROUTING = new Map([
  ["/photo/",     new Set([".jpg", ".jpeg", ".gif", ".webp", ".png"])],
  ["/atb/",       new Set([".mp3", ".m4a"])],
  ["/artist/",    new Set([".mp3"])],           // images → Pages (content/artist/)
  ["/beefheart/", new Set([".mp3"])],           // images → Pages (content/beefheart/)
  ["/calendar/",  new Set([".mp3"])],           // images → Pages (bluesru-arc/calendar/)
  ["/bluesnews/", new Set([".rm", ".ra"])],     // images → Pages (content/bluesnews/)
  ["/efes/",      new Set([".rm"])],            // images → Pages (content/efes/)
  ["/mojobook/",  new Set([".rm"])],            // images → Pages (content/mojobook/)
  ["/rblues/",    new Set([".mp3", ".rm", ".ra", ".avi", ".wmv", ".mpg", ".mid", ".jpg", ".jpeg"])],
  ["/video/",     new Set([".rm"])],
  ["/ww/",        new Set([".rm", ".mp3", ".wma"])],
]);

// Flat set of all extensions handled by R2 (for the bare-404 fast-return below).
const MEDIA_EXTENSIONS = new Set([...R2_ROUTING.values()].flatMap(s => [...s]));

// URL prefixes for /atb/ sub-paths stored under different R2 dir names.
const CUSTOM_DIR_PREFIXES = [
  ["/atb/excerpts/", "excerpts/"],
  ["/atb/kalachev-kostin-show/", "kalachev-kostin-show/"],
];

function resolveMediaUrl(pathname) {
  const dot = pathname.lastIndexOf(".");
  if (dot < 0) return null;
  const ext = pathname.slice(dot).toLowerCase();

  // Find the prefix entry; if missing or extension not in its R2 set → fall through
  let matched = false;
  for (const [prefix, exts] of R2_ROUTING) {
    if (pathname.startsWith(prefix)) {
      if (!exts.has(ext)) return null;
      matched = true;
      break;
    }
  }
  if (!matched) return null;

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

  // ── Canonical host redirect: www → bare, http → https ────────────────────
  const isWww = url.hostname.startsWith("www.");
  const isHttp = url.protocol === "http:";
  if (isWww || isHttp) {
    const canonical = new URL(request.url);
    canonical.protocol = "https:";
    if (isWww) canonical.hostname = url.hostname.slice(4);
    return Response.redirect(canonical.toString(), 301);
  }

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

  // ── /news/?iid=N → /news/YYYY/MM/DD/storyN/ (manifest lookup) ─────────────
  if ((pathname === "/news/" || pathname === "/news/default.aspx") && searchParams.has("iid")) {
    const iid = searchParams.get("iid");
    const m = await getManifest(env, request.url);
    const target = m.news_iid && m.news_iid[iid];
    if (target) return redirect301(target, request.url);
    return redirect301("/news/", request.url);
  }

  // ── /links/?catid=N → /links/ (no per-category page in new layout) ────────
  if (pathname === "/links/" && searchParams.has("catid")) {
    return redirect301("/links/", request.url);
  }

  // ── /data/albumsearch.aspx?artistname=X → /artist/{slug}/ (manifest) ──────
  if (pathname === "/data/albumsearch.aspx" || pathname === "/albumsearch.aspx") {
    const name = searchParams.get("artistname");
    if (name) {
      const m = await getManifest(env, request.url);
      // normalize: lowercase, ASCII alphanum-and-space
      const norm = name.toLowerCase().normalize("NFKD")
        .replace(/[^a-z0-9]+/g, " ").trim();
      const target = m.artist_names && m.artist_names[norm];
      if (target) return redirect301(target, request.url);
    }
    return redirect301("/artist/", request.url);
  }

  // ── Forum page*.html → page* (strip .html from pagination URLs) ──────────
  const forumPageMatch = pathname.match(/^(\/forum\/page\d+)\.html$/);
  if (forumPageMatch) {
    return redirect301(forumPageMatch[1], request.url);
  }

  // ── Forum branch URLs → topic page ───────────────────────────────────────
  // /forum/topic{N}/branch{M} only exists in Google's index from the old site
  const branchMatch = pathname.match(/^\/forum\/(topic\d+)\/branch\d+\/?$/);
  if (branchMatch) {
    return redirect301(`/forum/${branchMatch[1]}`, request.url);
  }

  // ── Legacy /bluesmen/ directory redirects ─────────────────────────────────
  if (pathname.startsWith("/bluesmen/")) {
    const m = await getManifest(env, request.url);
    if (m.bluesmen) {
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

    if (r2Response.status === 404) {
      return new Response("", { status: 404 });
    }
    const headers = new Headers(r2Response.headers);
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set("Cache-Control", "public, max-age=86400");
    return new Response(r2Response.body, {
      status: r2Response.status,
      headers,
    });
  }

  const response = await context.next();
  if (response.status === 404) {
    const dot = pathname.lastIndexOf(".");
    if (dot >= 0) {
      const ext = pathname.slice(dot).toLowerCase();
      if (MEDIA_EXTENSIONS.has(ext) || ext === ".xml") {
        return new Response("", { status: 404 });
      }
    }
  }
  return response;
}
