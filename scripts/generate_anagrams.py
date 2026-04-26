#!/usr/bin/env python3
"""Generate static anagrams page from fedor/anagrams.xml."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import os
ARC = Path(__file__).resolve().parent.parent
_ws = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
SITE = Path(os.environ.get('BLUESRU_SITE', str(_ws / 'bluesru-site')))
SRC_XML = _ws / 'blues-ru' / 'fedor' / 'anagrams.xml'
CONTENT_XML = ARC / 'content' / 'fedor' / 'anagrams.xml'

def load_groups():
    xml_path = CONTENT_XML if CONTENT_XML.exists() else SRC_XML
    # Parse windows-1251 XML
    raw = xml_path.read_bytes().replace(b'windows-1251', b'utf-8')
    text = raw.decode('windows-1251').encode('utf-8')
    root = ET.fromstring(text)
    groups = []
    for section in root:
        section_name = section.tag  # 'short' or 'long'
        for group in section.findall('group'):
            words = [w.text for w in group.findall('word') if w.text]
            if words:
                groups.append({
                    'words': words,
                    'max_diff': int(group.get('max-diff', 0)),
                    'max_len': max(len(w) for w in words),
                    'section': section_name,
                })
    return groups

def generate():
    groups = load_groups()
    data_json = json.dumps(groups, ensure_ascii=False)

    FOOTER = (ARC / 'includes' / 'footer.inc').read_text(encoding='utf-8').strip()
    GA_ID = 'G-8HDC1W9R3E'
    ga_snippet = f'''<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>'''

    html = f'''<!DOCTYPE html>
<html>
<head>
<title>Анаграммы - Blues.Ru</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="shortcut icon" href="/images/bluesru.ico">
<style>
  body {{ max-width: 900px; margin: 0 auto; padding: 0 1em; }}
</style>
{ga_snippet}
</head>
<body bgcolor="#FFFFFF" text="#000000" link="#0000FF" vlink="#5511CC" alink="#00BB00">

<p><a href="/"><b>Blues.Ru</b></a> &gt; <a href="/fedor/">Федор Романенко</a> &gt; Анаграммы</p>

<p>Файл с анаграммами русского языка, откопанный из архива 1993 года.</p>

<form id="sort-form">
  Порядок сортировки:
  <select id="sort-select" onchange="renderList()">
    <option value="0">По количеству перестановок</option>
    <option value="1">Длинные, потом короткие</option>
    <option value="2">По длине</option>
    <option value="3">По алфавиту</option>
  </select>
  &#32;
  <input type="button" value="Показать" onclick="renderList()">
</form>

<ul id="anagram-list"><li><i>загрузка...</i></li></ul>

<p align="center">
{FOOTER}
</p>

<script>
var GROUPS = {data_json};

function sortedGroups(mode) {{
  var g = GROUPS.slice();
  if (mode === 0) {{
    g.sort(function(a,b){{
      if (b.max_diff !== a.max_diff) return b.max_diff - a.max_diff;
      if (b.max_len !== a.max_len) return b.max_len - a.max_len;
      return a.words[0] < b.words[0] ? -1 : 1;
    }});
  }} else if (mode === 1) {{
    g.sort(function(a,b){{
      if (a.section !== b.section) return a.section === 'long' ? -1 : 1;
      return a.words[0] < b.words[0] ? -1 : 1;
    }});
  }} else if (mode === 2) {{
    g.sort(function(a,b){{
      if (b.max_len !== a.max_len) return b.max_len - a.max_len;
      return a.words[0] < b.words[0] ? -1 : 1;
    }});
  }} else {{
    g.sort(function(a,b){{ return a.words[0] < b.words[0] ? -1 : 1; }});
  }}
  return g;
}}

function renderList() {{
  var mode = parseInt(document.getElementById('sort-select').value, 10);
  var groups = sortedGroups(mode);
  var html = '';
  groups.forEach(function(g) {{
    html += '<li>' + g.words.join(' - ') + '</li>';
  }});
  document.getElementById('anagram-list').innerHTML = html;
}}

renderList();
</script>
</body>
</html>
'''
    out = SITE / 'fedor' / 'anagrams' / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8')
    print(f'  fedor/anagrams/index.html: {len(groups)} groups')

if __name__ == '__main__':
    generate()
