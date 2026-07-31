/* "Весь этот блюз" seasonal picker.
   Re-ranks the archived ATB shows against the visitor's actual date, so the
   block rotates day-to-day without a rebuild. Most shows mark a bluesman's
   birth/death anniversary, so aligning by calendar day (ignoring year) keeps
   them relevant across years.

   Any element carrying data-atb-seasonal is a mount point:
     data-atb-seasonal="homepage" — renders <li> rows into a widget-list <ul>
     data-atb-seasonal="index"    — renders <p> rows for the /atb/ page top
   Optional data-count (default 5) caps how many shows are shown.
   Server-rendered fallback content stays put until the JSON loads. */
(function () {
  var mounts = document.querySelectorAll('[data-atb-seasonal]');
  if (!mounts.length) return;

  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var DAY = 86400000;

  // Days from today to the next occurrence of a MM-DD (today = 0, wraps a year).
  function dayDistance(md) {
    var mo = parseInt(md.slice(0, 2), 10) - 1;
    var da = parseInt(md.slice(3), 10);
    if (isNaN(mo) || isNaN(da)) return 1e9;
    var target = new Date(today.getFullYear(), mo, da);
    if (target < today) target = new Date(today.getFullYear() + 1, mo, da);
    return Math.round((target - today) / DAY);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function pick(shows, count) {
    return shows
      .map(function (s) { return { s: s, d: dayDistance(s.md || (s.date || '').slice(5)) }; })
      // Nearest upcoming anniversary first; ties broken by the more recent recording.
      .sort(function (a, b) { return a.d - b.d || (b.s.date < a.s.date ? -1 : b.s.date > a.s.date ? 1 : 0); })
      .slice(0, count)
      .map(function (x) { return x.s; });
  }

  function artistsHtml(ep, small) {
    if (!ep.artists || !ep.artists.length) return '';
    var links = ep.artists.map(function (a) {
      return '<a href="/artist/' + esc(a.slug) + '/#atb">' + esc(a.name || a.slug) + '</a>';
    }).join(', ');
    return ' &mdash; ' + (small ? '<small>' + links + '</small>' : links);
  }

  function renderHomepage(ep) {
    return '<li><span class="widget-date"><font color="#4F62B5">' + esc(ep.date) + '</font></span>'
      + '&ensp;<a href="' + esc(ep.url) + '">' + esc(ep.summary) + '</a>'
      + artistsHtml(ep, true) + '</li>';
  }

  function renderIndex(ep) {
    return '<p><span class="ep-date">' + esc(ep.date) + '</span> '
      + '<a href="' + esc(ep.url) + '">' + esc(ep.summary) + '</a></p>';
  }

  fetch('/data/atb/seasonal.json')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (shows) {
      if (!shows || !shows.length) return;
      mounts.forEach(function (el) {
        var count = parseInt(el.getAttribute('data-count'), 10) || 5;
        var render = el.getAttribute('data-atb-seasonal') === 'homepage' ? renderHomepage : renderIndex;
        el.innerHTML = pick(shows, count).map(render).join('\n');
      });
    })
    .catch(function () { /* keep server-rendered fallback */ });
})();
