(function () {
  if (window._contactJsLoaded) return;
  window._contactJsLoaded = true;
  var u = 'arc', d = 'blues.ru';
  var addr = u + '@' + d;
  document.querySelectorAll('.contact-email').forEach(function (el) {
    var a = document.createElement('a');
    a.href = 'mailto:' + addr;
    a.textContent = addr;
    el.appendChild(a);
  });
  document.querySelectorAll('.contact-email-plain').forEach(function (el) {
    el.textContent = addr;
  });
})();
