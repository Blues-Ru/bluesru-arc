// Efes mobile responsive layout
(function() {
  var isMobile = window.innerWidth <= 680;
  if (!isMobile) return;

  // Find the main 2-row layout table
  var tables = document.querySelectorAll('body > table');
  var layoutTable = null;
  for (var i = 0; i < tables.length; i++) {
    var rows = tables[i].querySelectorAll('tr');
    if (rows.length >= 2) { layoutTable = tables[i]; break; }
  }
  if (!layoutTable) return;

  var rows = layoutTable.querySelectorAll('tr');
  // Last row: nav cell (first td) + content cell (last td)
  var navRow = rows[rows.length - 1];
  var navCell = navRow.cells[0];
  var contentCell = navRow.cells[navRow.cells.length - 1];
  if (!navCell || !contentCell || navCell === contentCell) return;

  // Restructure: table → flex column, content first
  layoutTable.style.display = 'block';
  layoutTable.style.width = '100%';

  // Wrap the table in a flex container that puts content first
  var wrapper = document.createElement('div');
  wrapper.style.cssText = 'display:flex;flex-direction:column;width:100%';
  layoutTable.parentNode.insertBefore(wrapper, layoutTable);
  wrapper.appendChild(layoutTable);

  // Move content cell out before nav
  var contentDiv = document.createElement('div');
  contentDiv.style.cssText = 'width:100%;box-sizing:border-box;padding:0';
  while (contentCell.firstChild) contentDiv.appendChild(contentCell.firstChild);

  var navDiv = document.createElement('div');
  navDiv.style.cssText = 'width:100%;box-sizing:border-box;border-top:1px solid #ccc;margin-top:8px;padding-top:4px';

  // Add toggle button for nav
  var btn = document.createElement('button');
  btn.textContent = '☰ Навигация';
  btn.style.cssText = 'display:block;width:100%;background:#8B0000;color:#fff;border:none;padding:8px 12px;font-size:1em;text-align:left;cursor:pointer;margin-bottom:4px';
  var navInner = document.createElement('div');
  navInner.style.display = 'none';
  while (navCell.firstChild) navInner.appendChild(navCell.firstChild);
  btn.onclick = function() {
    navInner.style.display = navInner.style.display === 'none' ? 'block' : 'none';
    btn.textContent = navInner.style.display === 'none' ? '☰ Навигация' : '✕ Навигация';
  };
  navDiv.appendChild(btn);
  navDiv.appendChild(navInner);

  // Hide the original table rows
  layoutTable.style.display = 'none';

  wrapper.insertBefore(contentDiv, layoutTable);
  wrapper.appendChild(navDiv);
})();
