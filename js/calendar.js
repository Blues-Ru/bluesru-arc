/* Blues calendar widget.
   data-mode="short" (homepage): today only, 2 full events + compact "также сегодня" line
   default (calendar page):       yesterday / today / tomorrow, full representation
*/
(function() {
  var el = document.getElementById('blues-calendar');
  if (!el) return;

  var shortMode = el.getAttribute('data-mode') === 'short';
  var now = new Date();
  var currentYear = now.getFullYear();

  function toMmDd(d) {
    return String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function addDays(d, n) {
    var r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
  }
  function formatDDMM(mmdd) {
    return mmdd.slice(3) + '.' + mmdd.slice(0, 2);
  }
  function typePrefix(ev) {
    if (ev.type === 'born') return 'род.\u00a0';
    if (ev.type === 'died') return 'ум.\u00a0';
    return '';
  }

  function renderEventFull(ev) {
    var year = parseInt(ev.year, 10);
    var diff = currentYear - year;
    var agoStr = diff > 0 ? ' (' + diff + ' г. назад)' : '';
    var yearLink = '<a href="/calendar/' + ev.year + '/">' + ev.year + ' году</a>';
    var header = '<a name="' + ev.id + '">В ' + yearLink + agoStr + '</a>';
    var html = '<p>';
    if (ev.picture) {
      html += '<img src="/calendar/images/' + ev.picture + '" border="0" align="right" vspace="4" hspace="8" style="max-width:180px;max-height:120px;">';
    }
    html += header + ' ' + ev.text;
    if (ev.picture) html += '<br clear="both">';
    html += '</p>';
    return html;
  }

  function renderDayFull(mmdd, events, label, dateId) {
    var evHtml = events.length
      ? events.map(renderEventFull).join('')
      : '<p><i>Нет событий</i></p>';
    var idAttr = dateId ? ' id="' + dateId + '"' : '';
    return '<div' + idAttr + '><h3 style="margin:0.8em 0 0.3em">' + label + '</h3>'
      + evHtml
      + '<hr size="1"></div>';
  }

  function renderShort(calData) {
    var mmdd = toMmDd(now);
    var events = (calData && calData[mmdd]) || [];
    var label = formatDDMM(mmdd) + ' (сегодня)';
    var html = '<b>' + label + '</b><br>';

    if (!events.length) {
      html += '<p><i>Нет событий</i></p>';
    } else {
      var FULL_COUNT = 2;
      events.slice(0, FULL_COUNT).forEach(function(ev) { html += renderEventFull(ev); });
      var rest = events.slice(FULL_COUNT);
      if (rest.length) {
        var calUrl = '/calendar/';
        var parts = rest.map(function(ev) {
          var pfx = typePrefix(ev);
          var name = ev.title || ev.text.replace(/<[^>]+>/g, '').slice(0, 40);
          var year = parseInt(ev.year, 10);
          var diff = year > 0 ? currentYear - year : 0;
          var ago = (ev.type === 'born' || ev.type === 'died') && diff > 0
            ? ' <small style="color:#999">(' + diff + '\u00a0г.\u00a0назад)</small>' : '';
          return pfx + '<a href="/calendar/' + ev.year + '/#' + ev.id + '">' + name + '</a>' + ago;
        });
        html += '<p>также сегодня: ' + parts.join(', ')
             + ' <a href="' + calUrl + '">(' + events.length + ' соб.) &gt;&gt;&gt;&gt;&gt;</a></p>';
      }
    }
    el.innerHTML = html;
  }

  function renderFull(calData) {
    var yesterday = addDays(now, -1);
    var tomorrow  = addDays(now, +1);
    var days = [
      { date: yesterday, mmdd: toMmDd(yesterday), label: formatDDMM(toMmDd(yesterday)) },
      { date: now,       mmdd: toMmDd(now),       label: formatDDMM(toMmDd(now)) + ' (сегодня)' },
      { date: tomorrow,  mmdd: toMmDd(tomorrow),  label: formatDDMM(toMmDd(tomorrow)) },
    ];
    var html = '';
    days.forEach(function(day) {
      var events = (calData && calData[day.mmdd]) || [];
      var y = day.date.getFullYear();
      var m = String(day.date.getMonth() + 1).padStart(2, '0');
      var d = String(day.date.getDate()).padStart(2, '0');
      html += renderDayFull(day.mmdd, events, day.label, y + '-' + m + '-' + d);
    });
    el.innerHTML = html;
    var hash = window.location.hash;
    if (hash) {
      var id = hash.slice(1);
      var target = document.getElementById(id);
      if (target) target.scrollIntoView();
    }
  }

  function fetchDay(mmdd) {
    return fetch('/data/calendar/' + mmdd + '.json')
      .then(function(r) { return r.ok ? r.json() : []; })
      .catch(function() { return []; });
  }

  var days = shortMode
    ? [toMmDd(now)]
    : [toMmDd(addDays(now, -1)), toMmDd(now), toMmDd(addDays(now, +1))];

  Promise.all(days.map(fetchDay))
    .then(function(results) {
      var calData = {};
      days.forEach(function(mmdd, i) { calData[mmdd] = results[i]; });
      shortMode ? renderShort(calData) : renderFull(calData);
    })
    .catch(function() { el.innerHTML = '<p><i>Ошибка загрузки календаря.</i></p>'; });
})();
