function initGallery(photos) {
  var cur = 0;
  var lb = document.getElementById('lb');
  function show(i) {
    cur = ((i % photos.length) + photos.length) % photos.length;
    document.getElementById('lb-img').src = photos[cur].file;
    document.getElementById('lb-caption').textContent = photos[cur].caption || '';
    document.getElementById('lb-counter').textContent = (cur+1) + ' / ' + photos.length;
    lb.classList.add('open');
  }
  document.getElementById('grid').addEventListener('click', function(e) {
    var a = e.target.closest('a[data-idx]');
    if (a) { e.preventDefault(); show(parseInt(a.dataset.idx)); }
  });
  document.getElementById('lb-prev').addEventListener('click', function(){ show(cur-1); });
  document.getElementById('lb-next').addEventListener('click', function(){ show(cur+1); });
  document.getElementById('lb-close').addEventListener('click', function(){ lb.classList.remove('open'); });
  document.addEventListener('keydown', function(e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'ArrowLeft')  show(cur-1);
    if (e.key === 'ArrowRight') show(cur+1);
    if (e.key === 'Escape')     lb.classList.remove('open');
  });
  lb.addEventListener('click', function(e) {
    if (e.target === lb) lb.classList.remove('open');
  });
}
