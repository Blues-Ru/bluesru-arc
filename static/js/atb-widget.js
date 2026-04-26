// ATB (Весь Этот Блюз) homepage widget
// Loads /data/latest-atb.json and renders into #atb-latest
(function () {
  var el = document.getElementById('atb-latest');
  if (!el) return;

  fetch('/data/latest-atb.json')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) { el.innerHTML = ''; return; }
      var html = '<ul>';
      for (var i = 0; i < items.length; i++) {
        var ep = items[i];
        var date = ep.date ? '<small style="color:#777">' + ep.date + '</small> ' : '';
        html += '<li>' + date + '<a href="' + ep.url + '">' + ep.summary + '</a></li>\n';
      }
      html += '</ul>';
      el.innerHTML = html;
    })
    .catch(function () { el.innerHTML = ''; });
})();
