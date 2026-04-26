/* Load artist album list from pre-generated JSON and inject into page. */
(function() {
  var el = document.getElementById('artist-albums');
  if (!el) return;
  var slug = el.getAttribute('data-slug');
  if (!slug) return;

  fetch('/data/artists/' + slug + '.json')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data || !data.albums || !data.albums.length) { el.innerHTML = ''; return; }
      var html = '<h3>Избранные компакт-диски</h3><ul>';
      data.albums.forEach(function(a) {
        var artistSlug = slug;  // artist's own slug
        var title = a.title || a.artist || data.name;
        var year = a.year ? ', ' + a.year : '';
        var labelStr = a.label ? ', <i>' + a.label + '</i>' : '';
        // Strip artist prefix from album URL segment (e.g. albert-collins-cold-snap → cold-snap)
        var albumUrlSlug = a.slug || '';
        if (albumUrlSlug && artistSlug && albumUrlSlug.indexOf(artistSlug + '-') === 0) {
          albumUrlSlug = albumUrlSlug.slice(artistSlug.length + 1);
        }
        var href = albumUrlSlug
          ? '/artist/' + artistSlug + '/' + albumUrlSlug + '/'
          : (a.review_slug ? '/review/' + a.review_slug + '/' : '/data/albumview.aspx?cdid=' + a.id);
        var cover = a.asin
          ? '<img src="http://images.amazon.com/images/P/' + a.asin + '.01.THUMBZZZ.jpg" alt="" border="0" style="vertical-align:middle;margin-right:4px;" width="40" height="40">'
          : '';
        html += '<li>' + cover + '<b><a href="' + href + '">' + title + '</a></b>';
        if (a.artist && a.artist !== data.name) html += ', ' + a.artist;
        html += year + labelStr + '</li>';
      });
      html += '</ul>';
      el.innerHTML = html;
    })
    .catch(function() { el.innerHTML = ''; });
})();
