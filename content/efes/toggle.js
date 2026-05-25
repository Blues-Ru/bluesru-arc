// Efes mobile responsive layout — restructure 2x2 table into nav-on-top stack.
(function() {
  function restructure() {
    if (window.innerWidth > 680) return;
    if (document.body.dataset.efesMobile) return;

    var tables = document.querySelectorAll('body > table');
    var layoutTable = null;
    for (var i = 0; i < tables.length; i++) {
      if (tables[i].querySelectorAll('tr').length >= 2) {
        layoutTable = tables[i];
        break;
      }
    }
    if (!layoutTable) return;

    var rows = layoutTable.querySelectorAll('tr');
    var titleRow = rows[0];
    var navRow = rows[rows.length - 1];
    var titleCell = titleRow.cells[titleRow.cells.length - 1];
    var navCell = navRow.cells[0];
    var contentCell = navRow.cells[navRow.cells.length - 1];
    if (!navCell || !contentCell || navCell === contentCell) return;

    document.body.dataset.efesMobile = '1';

    var navDiv = document.createElement('div');
    navDiv.className = 'efes-mobile-nav';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'efes-mobile-nav-toggle';
    btn.textContent = '☰ Навигация';

    var navInner = document.createElement('div');
    navInner.className = 'efes-mobile-nav-inner';
    while (navCell.firstChild) navInner.appendChild(navCell.firstChild);

    btn.addEventListener('click', function() {
      var open = navDiv.classList.toggle('open');
      btn.textContent = (open ? '✕' : '☰') + ' Навигация';
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    btn.setAttribute('aria-expanded', 'false');
    navDiv.appendChild(btn);
    navDiv.appendChild(navInner);

    var titleDiv = document.createElement('div');
    titleDiv.className = 'efes-mobile-title';
    while (titleCell.firstChild) titleDiv.appendChild(titleCell.firstChild);

    var contentDiv = document.createElement('div');
    contentDiv.className = 'efes-mobile-content';
    while (contentCell.firstChild) contentDiv.appendChild(contentCell.firstChild);

    layoutTable.style.display = 'none';
    var parent = layoutTable.parentNode;
    parent.insertBefore(navDiv, layoutTable);
    parent.insertBefore(titleDiv, layoutTable);
    parent.insertBefore(contentDiv, layoutTable);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', restructure);
  } else {
    restructure();
  }
  window.addEventListener('resize', restructure);
})();
