/* Load latest blues-data news headers from pre-generated JSON and inject into homepage. */
(function() {
  var el = document.getElementById('blues-news-headers');
  if (!el) return;

  fetch('/data/latest-blues-news.json')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data || !data.items || !data.items.length) return;
      var html = '';
      data.items.forEach(function(item) {
        var date = item.date ? '<font color="#4F62B5">' + item.date + '</font> ' : '';
        var title = item.title ? item.title : '(без заголовка)';
        html += '<li>' + date + '<a href="' + item.url + '">' + title + '</a></li>';
      });
      el.innerHTML = '<ul>' + html + '</ul>';
    })
    .catch(function() {});
})();
