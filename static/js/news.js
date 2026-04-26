/* Load latest site news from pre-generated JSON and inject into page. */
(function() {
  var el = document.getElementById('site-news');
  if (!el) return;

  fetch('/data/latest-news.json')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data || !data.items || !data.items.length) return;
      var html = '';
      var items = data.items.slice(0, 10);
      items.forEach(function(item) {
        var date = item.date ? '<font color="#4F62B5">' + item.date + '</font>&nbsp;&nbsp;&nbsp;' : '';
        html += '<li>' + date + item.text + '</li>';
      });
      el.innerHTML = '<ul>' + html + '</ul>';
    })
    .catch(function() {});
})();
