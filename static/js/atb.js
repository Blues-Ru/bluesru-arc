function atbSeek(partIdx, sec) {
  var pl = document.querySelectorAll('.atb-audio audio');
  var audio = pl[partIdx];
  if (!audio) return;
  var doSeek = function() { audio.currentTime = sec; audio.play().catch(function(){}); };
  if (audio.readyState >= 1) { doSeek(); }
  else { audio.addEventListener('loadedmetadata', doSeek, {once: true}); audio.load(); }
}
function atbSeekHash() {
  var m = /^#p(\d+)t(\d+)$/.exec(location.hash);
  if (m) atbSeek(parseInt(m[1]), parseInt(m[2]));
}
window.addEventListener('load', atbSeekHash);
window.addEventListener('hashchange', atbSeekHash);
