// ── State ─────────────────────────────────────────────────────────────────────
var selectedLetter = null;

// ── Computed stats (computed once on load) ────────────────────────────────────
var _stats = null;
var _totalPrimary = 0;

function computeStats() {
  if (_stats) return _stats;
  _stats = {};
  _totalPrimary = 0;
  document.querySelectorAll('.artist-entry:not(.artist-xref)').forEach(function(e) {
    _totalPrimary++;
    (e.getAttribute('data-res') || '').split(/\s+/).forEach(function(t) {
      if (t) _stats[t] = (_stats[t] || 0) + 1;
    });
  });
  return _stats;
}

// ── Type helpers ──────────────────────────────────────────────────────────────
var _TYPE_LABELS = {
  review: 'Обзоры', article: 'Статья', interview: 'Интервью',
  atb: 'Весь этот блюз', photo: 'Фото', page: 'Страница',
  calendar: 'Календарь', spotify: 'Spotify', apple_music: 'Apple Music',
  deezer: 'Deezer', ytmusic: 'YouTube Music',
  lyrics: 'Тексты', tabs: 'Ноты', press: 'Пресса',
};

function getCheckedTypes() {
  var types = new Set();
  document.querySelectorAll('.res-type-check:checked').forEach(function(cb) {
    types.add(cb.value);
  });
  return types;
}

function entryMatchesTypes(entry, types) {
  if (types.size === 0) return false;
  var res = (entry.getAttribute('data-res') || '').split(/\s+/);
  return res.some(function(t) { return t && types.has(t); });
}

// ── URL fragment state ────────────────────────────────────────────────────────

// Resolve a slug-style hash (e.g. "delbert-mcclinton") to its anchor element,
// setting selectedLetter to the containing letter section. Returns the element
// or null if not found.
function resolveSlugAnchor(hash) {
  if (!hash || hash.indexOf(':') >= 0) return null;
  // Single uppercase letter or '#' — handled as letter code, not a slug
  if (/^[A-Z#]$/.test(hash)) return null;
  var anchor = document.querySelector('a[name="' + hash + '"]');
  if (!anchor) return null;
  var sec = anchor.closest('.letter-section');
  if (!sec) return null;
  selectedLetter = sec.getAttribute('data-letter');
  return anchor;
}

function readFragment() {
  var hash = location.hash.slice(1);
  if (!hash) return null;
  var parts = hash.split(':');
  var letter = parts[0] || null;
  var types = parts[1] ? parts[1].split(',').filter(Boolean) : null;
  if (letter && letter.length === 1 && /[A-Z]/.test(letter)) {
    selectedLetter = letter;
    if (types) {
      document.querySelectorAll('.res-type-check').forEach(function(cb) {
        cb.checked = types.indexOf(cb.value) >= 0;
      });
    }
    return null;
  }
  // Not a letter code — try to resolve as a slug anchor
  return resolveSlugAnchor(parts[0]);
}

function writeFragment() {
  var types = [];
  document.querySelectorAll('.res-type-check:checked').forEach(function(cb) {
    types.push(cb.value);
  });
  var hash = (selectedLetter || '') + ':' + types.join(',');
  history.replaceState(null, '', '#' + hash);
}

// ── Status text ───────────────────────────────────────────────────────────────
function updateStatus(visibleCount, searching) {
  var el = document.getElementById('bluesmen-status');
  if (!el) return;
  var stats = computeStats();
  if (!searching && selectedLetter === null) {
    // Default state: show total + per-type stats
    var statLines = [];
    var typeOrder = ['atb', 'photo', 'calendar', 'review', 'article', 'interview',
                     'page', 'spotify', 'apple_music', 'ytmusic', 'deezer'];
    typeOrder.forEach(function(t) {
      if (stats[t]) {
        statLines.push((_TYPE_LABELS[t] || t) + ' — ' + stats[t]);
      }
    });
    el.innerHTML = '<div class="status-default"><b>' + _totalPrimary + ' музыкантов:</b> поищите или выберите первую букву'
      + (statLines.length ? '<br><small class="status-stats">' + statLines.join('<br>') + '</small>' : '')
      + '</div>';
  } else if (visibleCount === 0) {
    el.innerHTML = '<div class="status-empty">Нет музыкантов</div>';
  } else {
    el.innerHTML = '';
  }
}

// ── Main filter function ──────────────────────────────────────────────────────
function applyFilters(fromInput) {
  var query = (document.getElementById('artist-filter').value || '').toLowerCase().trim();
  var terms = query ? query.split(/\s+/).filter(Boolean) : [];
  var types = getCheckedTypes();
  var searching = terms.length > 0;

  // Only reset letter when user manually clears the search box
  if (fromInput && !searching && query === '') {
    selectedLetter = null;
  }

  var visibleCount = 0;

  document.querySelectorAll('.letter-section').forEach(function(sec) {
    var letter = sec.getAttribute('data-letter');
    var letterMatch = searching ? true : (selectedLetter !== null && letter === selectedLetter);
    var secVisible = false;

    sec.querySelectorAll('.artist-entry').forEach(function(entry) {
      var isXref = entry.classList.contains('artist-xref');
      // Hide xrefs in search mode
      if (searching && isXref) {
        entry.classList.remove('visible');
        return;
      }
      var nameMatch = terms.length === 0 || terms.every(function(t) {
        return (entry.getAttribute('data-name') || '').indexOf(t) >= 0;
      });
      var typeMatch = entryMatchesTypes(entry, types);
      var visible = letterMatch && nameMatch && typeMatch;
      entry.classList.toggle('visible', visible);
      if (visible) { secVisible = true; if (!isXref) visibleCount++; }
    });
    sec.classList.toggle('visible', secVisible);
  });

  updateLetterNav(searching);
  updateStatus(visibleCount, searching);
  writeFragment();
}

function updateLetterNav(searching) {
  document.querySelectorAll('.letter-nav a[data-letter]').forEach(function(a) {
    var isSel = !searching && a.getAttribute('data-letter') === selectedLetter;
    a.style.fontWeight = isSel ? 'bold' : '';
    a.style.textDecoration = isSel ? 'none' : '';
  });
}

// ── Letter click ──────────────────────────────────────────────────────────────
function selectLetter(letter) {
  selectedLetter = (selectedLetter === letter) ? null : letter;
  document.getElementById('artist-filter').value = '';
  applyFilters();
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.querySelectorAll('.res-type-check').forEach(function(cb) {
  cb.addEventListener('change', applyFilters);
});

// Handle in-page xref clicks: hashchange fires when #slug changes
window.addEventListener('hashchange', function() {
  var anchorEl = resolveSlugAnchor(location.hash.slice(1));
  if (anchorEl) {
    applyFilters();
    setTimeout(function() { anchorEl.scrollIntoView({block: 'center'}); }, 0);
  }
});

var _initAnchor = readFragment();
applyFilters();
if (_initAnchor) {
  setTimeout(function() { _initAnchor.scrollIntoView({block: 'center'}); }, 0);
}
