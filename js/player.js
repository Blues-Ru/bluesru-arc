(function () {
  'use strict';
  var COOKIE = 'bluesru_player';

  function getCookie(name) {
    var m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : '';
  }

  function setCookie(name, val) {
    var exp = new Date();
    exp.setFullYear(exp.getFullYear() + 1);
    document.cookie = name + '=' + encodeURIComponent(val)
      + '; expires=' + exp.toUTCString() + '; path=/; SameSite=Lax';
  }

  function activatePlayer(platform) {
    document.querySelectorAll('.sp-frame').forEach(function (el) {
      el.style.display = 'none';
    });
    document.querySelectorAll('.stream-tab').forEach(function (el) {
      el.classList.remove('active');
    });

    if (platform) {
      var frame = document.getElementById('sp-' + platform);
      var tab = document.querySelector('.stream-tab[data-platform="' + platform + '"]');
      if (frame) {
        var iframe = frame.querySelector('iframe');
        if (iframe && !iframe.src && iframe.dataset.src) {
          iframe.src = iframe.dataset.src;
        }
        frame.style.display = 'block';
      }
      if (tab) tab.classList.add('active');
    } else {
      var noTab = document.querySelector('.stream-tab[data-platform=""]');
      if (noTab) noTab.classList.add('active');
    }
    setCookie(COOKIE, platform || '');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var tabs = document.querySelectorAll('.stream-tab');
    if (!tabs.length) return;

    var platforms = [];
    tabs.forEach(function (t) {
      if (t.dataset.platform) platforms.push(t.dataset.platform);
      t.addEventListener('click', function (e) {
        e.preventDefault();
        var p = this.dataset.platform || '';
        activatePlayer(p);
        if (p) {
          history.replaceState(null, '', '#' + p);
        } else {
          history.replaceState(null, '', location.pathname + location.search);
        }
      });
    });

    var hash = location.hash.replace('#', '');
    if (hash && platforms.indexOf(hash) !== -1) {
      activatePlayer(hash);
      return;
    }
    var saved = getCookie(COOKIE);
    if (saved && platforms.indexOf(saved) !== -1) {
      activatePlayer(saved);
    }
  });
}());
