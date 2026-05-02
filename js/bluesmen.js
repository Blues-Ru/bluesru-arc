function filterArtists(query) {
  var terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  var sections = document.querySelectorAll('.letter-section');
  sections.forEach(function(sec) {
    var entries = sec.querySelectorAll('.artist-entry');
    var sectionVisible = false;
    entries.forEach(function(e) {
      var name = e.getAttribute('data-name') || '';
      var match = terms.length === 0 || terms.every(function(t) { return name.indexOf(t) >= 0; });
      e.classList.toggle('visible', match);
      if (match) sectionVisible = true;
    });
    sec.classList.toggle('visible', sectionVisible || terms.length === 0);
  });
}
