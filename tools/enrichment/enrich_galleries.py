#!/usr/bin/env python3
"""
Enrich gallery YAML files with canonical_date, clean_title, slug, description.
Reads from data/galleries/ and updates per-gallery YAML files.
Uses LLM knowledge about blues events + data already in the YAMLs.
"""

import re
import yaml
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
GALLERIES_DIR = ARC / 'data' / 'galleries'
GALLERIES_YAML = GALLERIES_DIR / 'index.yaml'


def slugify(text):
    """Convert text to URL slug."""
    t = text.lower()
    # Transliterate common Russian chars
    tr = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
        'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
        'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    }
    result = ''
    for c in t:
        result += tr.get(c, c)
    result = re.sub(r'[^a-z0-9]+', '-', result)
    result = result.strip('-')
    return result[:60]


def parse_date_from_str(s):
    """Try to parse date strings like '23.04.2005', '17.X.2009', '03/10/02' etc."""
    if not s:
        return None
    # Roman numeral month map
    roman = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,
             'IX':9,'X':10,'XI':11,'XII':12}
    # DD.MM.YYYY
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # DD.Roman.YYYY
    m = re.search(r'(\d{1,2})\.(I{1,3}V?|VI{0,3}|IX|X[I]{0,3}|XI{1,2})\.(\d{4})', s)
    if m:
        mon = roman.get(m.group(2).upper())
        if mon:
            return f"{m.group(3)}-{mon:02d}-{int(m.group(1)):02d}"
    # MM/DD/YY or DD/MM/YY — ambiguous, skip
    # DD/MM/YY (European format most likely)
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', s)
    if m:
        d, mn, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y = 2000 + y if y <= 30 else 1900 + y
        if mn <= 12 and d <= 31:
            return f"{y:04d}-{mn:02d}-{d:02d}"
    # YYYY-MM-DD already
    m = re.match(r'^(\d{4}-\d{2}-\d{2})$', s.strip())
    if m:
        return m.group(1)
    return None


def year_from_path(path):
    """Extract year from gallery path."""
    top = path.split('/')[0].lstrip('_')
    m = re.search(r'((?:19|20)\d\d)', top)
    if m:
        return int(m.group(1))
    m = re.match(r'^(\d\d)[^0-9]', top)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy <= 30 else 1900 + yy
    m = re.search(r'(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    m = re.match(r'^(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy <= 30 else 1900 + yy
    return None


def date_from_path(path):
    """Extract YYYY-MM-DD or YYYY-MM from dated path segments like 13_02_16_Pardo."""
    # Pattern: YY_MM_DD in any segment
    m = re.search(r'(\d{2})_(\d{2})_(\d{2})', path)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        yyyy = 2000 + yy if yy <= 30 else 1900 + yy
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            return f"{yyyy:04d}-{mm:02d}-{dd:02d}"
    # Pattern: YYYY_MM_DD
    m = re.search(r'(20\d{2})_(\d{2})_(\d{2})', path)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Pattern: YYYYMMDD
    m = re.search(r'(20\d{2})(\d{2})(\d{2})', path)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


# ============================================================
# LLM-derived enrichment data for known galleries
# Format: path -> {canonical_date, clean_title, slug, description}
# ============================================================

ENRICHMENT = {
    # --- Year 2000 ---
    '00Autumn': {
        'canonical_date': '2000-10',
        'clean_title': 'XI Efes Pilsener Blues Festival 2000',
        'slug': 'efes-blues-festival-2000',
        'description': 'XI Efes Pilsener Blues Festival в Московском дворце молодёжи, 12–14 октября 2000. The Holmes Brothers, интервью и концертные фото.',
    },
    '00July': {
        'canonical_date': '2000-07',
        'clean_title': 'Блюз-новости июля 2000',
        'slug': 'blues-news-july-2000',
        'description': 'ATB Blues News, июль 2000: Buena Vista Social Club, новости из мира блюза.',
    },
    '00June': {
        'canonical_date': '2000-06',
        'clean_title': 'Блюз-новости июня 2000',
        'slug': 'blues-news-june-2000',
        'description': 'ATB Blues News, июнь 2000.',
    },
    '00May': {
        'canonical_date': '2000-05',
        'clean_title': 'Блюз-новости мая 2000',
        'slug': 'blues-news-may-2000',
        'description': 'ATB Blues News, май 2000.',
    },
    'Jan2000': {
        'canonical_date': '2000-01',
        'clean_title': 'Блюз-новости января 2000',
        'slug': 'blues-news-january-2000',
        'description': 'ATB Blues News, январь 2000.',
    },
    'Feb2000': {
        'canonical_date': '2000-02',
        'clean_title': 'Блюз-новости февраля 2000',
        'slug': 'blues-news-february-2000',
        'description': 'ATB Blues News, февраль 2000.',
    },
    'Mar2000': {
        'canonical_date': '2000-03',
        'clean_title': 'Блюз-новости марта 2000',
        'slug': 'blues-news-march-2000',
        'description': 'ATB Blues News, март 2000.',
    },
    'Apr2000': {
        'canonical_date': '2000-04',
        'clean_title': 'Блюз-новости апреля 2000',
        'slug': 'blues-news-april-2000',
        'description': 'ATB Blues News, апрель 2000.',
    },
    'Dec99': {
        'canonical_date': '1999-12',
        'clean_title': 'Блюз-новости декабря 1999',
        'slug': 'blues-news-december-1999',
        'description': 'ATB Blues News, декабрь 1999.',
    },

    # --- Year 2001 ---
    '01Winter': {
        'canonical_date': '2001-01',
        'clean_title': 'Блюз-новости зимы 2001',
        'slug': 'blues-news-winter-2001',
        'description': 'ATB Blues News, зима 2001: Bjørn Berge на Notodden, Son House, Double Trouble.',
    },
    'Notodden/Berge': {
        'canonical_date': '2001',
        'clean_title': 'Bjørn Berge at Notodden Blues Festival 2001',
        'slug': 'notodden-bjorn-berge-2001',
        'description': 'Bjørn Berge выступает на Notodden Blues Festival, Норвегия, 2001.',
    },
    'Notodden/Muss': {
        'canonical_date': '2001',
        'clean_title': 'Notodden Blues Festival 2001',
        'slug': 'notodden-blues-festival-2001',
        'description': 'Фотографии с Notodden Blues Festival 2001, Норвегия.',
    },

    # --- Year 2002 ---
    'Busk': {
        'canonical_date': '2002-05-25',
        'clean_title': 'Vidar Busk в Москве, май 2002',
        'slug': 'vidar-busk-moscow-2002',
        'description': 'Норвежский блюз-гитарист Vidar Busk в клубе B.B.King, Москва, 25–27 мая 2002.',
    },
    'Expt': {
        'canonical_date': '2002-10-03',
        'clean_title': 'Jam в Expat, 3 октября 2002',
        'slug': 'jam-expat-october-2002',
        'description': 'Блюз-джем в клубе Expat под руководством Dr. Аграновского, 3 октября 2002.',
    },
    'ZOO': {
        'canonical_date': '2002',
        'clean_title': 'Vive le Léopard d\'Amour, 2002',
        'slug': 'vive-le-leopard-damour-2002',
        'description': 'Фотогалерея Vive le Léopard d\'Amour, 2002.',
    },
    'DN': {
        'canonical_date': '2002',
        'clean_title': 'Фестиваль «Дельта Невы» 2002, Санкт-Петербург',
        'slug': 'delta-nevy-festival-2002',
        'description': 'II фестиваль «Дельта Невы» 2002, Санкт-Петербург — интервью участников и концертные фото.',
    },

    # --- Year 2003 ---
    '03Autumn': {
        'canonical_date': '2003-10',
        'clean_title': 'Блюз-новости осени 2003',
        'slug': 'blues-news-autumn-2003',
        'description': 'ATB Blues News, осень–зима 2003: Ragtime, джемы в B.B.King, блюз-фестиваль в Петрозаводске.',
    },
    '03Spring': {
        'canonical_date': '2003-03',
        'clean_title': 'Блюз-новости весны 2003',
        'slug': 'blues-news-spring-2003',
        'description': 'ATB Blues News, весна 2003.',
    },
    '03Winter': {
        'canonical_date': '2003-01',
        'clean_title': 'Блюз-новости зимы 2003',
        'slug': 'blues-news-winter-2003',
        'description': 'ATB Blues News, зима 2003.',
    },
    'hf03': {
        'canonical_date': '2002',
        'clean_title': 'Московский Харп-Фестиваль 2002',
        'slug': 'harp-festival-moscow-2002',
        'description': 'Московский фестиваль губной гармоники, 2002. Александр Братецкий, Максим Некрасов, Чистяков, Владимир Кожекин.',
    },
    'FedorOchakovo03': {
        'canonical_date': '2003',
        'clean_title': 'Фестиваль в Очаково, 2003',
        'slug': 'ochakovo-blues-festival-2003',
        'description': 'Блюз-фестиваль в Очаково, 2003. Фотографии Фёдора.',
    },
    'KidA': {
        'canonical_date': '2003-06',
        'clean_title': 'Kid Andersen & The Rock Awhile Band в Forte',
        'slug': 'kid-andersen-forte-2003',
        'description': 'Kid Andersen & The Rock Awhile Band (Норвегия) в клубе Forte, Москва, июнь 2003.',
    },
    'Lamb': {
        'canonical_date': '2003',
        'clean_title': 'Paul Lamb & the King Snakes в МХАТ',
        'slug': 'paul-lamb-kingsnakes-mhat-2003',
        'description': 'Paul Lamb & the King Snakes (Великобритания) выступают в МХАТ, Москва.',
    },
    'BiR': {
        'canonical_date': '2003',
        'clean_title': 'Blues in Russia',
        'slug': 'blues-in-russia',
        'description': 'Фотографии участников московской блюзовой сцены.',
    },
    'Rusbluz': {
        'canonical_date': '2003',
        'clean_title': 'Российский блюз',
        'slug': 'russian-blues',
        'description': 'Фотоколлекция российских блюзовых исполнителей.',
    },
    'Tiomma': {
        'canonical_date': '2003',
        'clean_title': 'Московская блюзовая сцена — фото Тёммы',
        'slug': 'moscow-blues-scene-tiomma',
        'description': 'Портреты московских блюзовых музыкантов: Аграновский, Каверкин, Ломидзе, Петрович.',
    },
    'rev': {
        'canonical_date': '2003',
        'clean_title': 'Blues Guitar Masters — портреты',
        'slug': 'blues-guitar-masters-portraits',
        'description': 'Портреты блюзовых гитаристов: Guy, Margolin, Thackery, Boudreau.',
    },

    # --- Year 2004 ---
    "'040416'": {
        'canonical_date': '2004-04-16',
        'clean_title': 'Блюзовый вечер, 16 апреля 2004',
        'slug': 'blues-evening-2004-04-16',
        'description': 'Фотографии с блюзового вечера 16 апреля 2004.',
    },
    '04Autumn/Efes04': {
        'canonical_date': '2004-10',
        'clean_title': 'Международный блюз-фестиваль 2004, Москва',
        'slug': 'efes-blues-festival-2004',
        'description': 'Международный блюз-фестиваль (бывший Efes Pilsener), Москва, октябрь 2004. Little Charlie & the Nightcats, Mighty Sam McClain, Fruitland Jackson. Джем в клубе B.B.King.',
    },
    '04Autumn/Harp': {
        'canonical_date': '2004-10',
        'clean_title': 'Харп-фестиваль, осень 2004',
        'slug': 'harp-festival-autumn-2004',
        'description': 'Московский фестиваль губной гармоники, осень 2004.',
    },
    '04Autumn/VDR': {
        'canonical_date': '2004-10',
        'clean_title': 'Дом у Дороги, осень 2004',
        'slug': 'dom-u-dorogi-autumn-2004',
        'description': 'Вечера в клубе «Дом у Дороги», осень 2004.',
    },
    '04Autumn/septjam': {
        'canonical_date': '2004-09',
        'clean_title': 'Сентябрьский джем 2004',
        'slug': 'september-jam-2004',
        'description': 'Блюзовый джем, сентябрь 2004.',
    },
    '04Smith': {
        'canonical_date': '2004',
        'clean_title': 'J.C. Smith в Москве, 2004',
        'slug': 'jc-smith-moscow-2004',
        'description': 'J.C. Smith выступает в Москве, 2004.',
    },
    '04Spring/0316SA': {
        'canonical_date': '2004-03-16',
        'clean_title': 'Svet & Al Boogie Band, 16 марта 2004',
        'slug': 'svet-al-boogie-band-2004-03-16',
        'description': 'Svet & Al Boogie Band «Happy with the Boogie» в Москве, 16 марта 2004. Фото А. Евдокимова.',
    },
    '04Spring/CDH27': {
        'canonical_date': '2004-04',
        'clean_title': 'CDH Blues, апрель 2004',
        'slug': 'cdh-blues-2004',
        'description': 'Блюзовый вечер в ЦДХ (Центральный дом художника), апрель 2004.',
    },
    '04Spring/HP': {
        'canonical_date': '2004-03',
        'clean_title': 'Запись на Арсенале, 2004',
        'slug': 'arsenal-studio-2004',
        'description': 'Участники фестиваля Blues.Ru в студии «Арсенал»: Юрий Каверкин, Svet & Al Boogie Band, Валерий Прохожий (Big Val).',
    },
    '04Spring/LN': {
        'canonical_date': '2004-04',
        'clean_title': 'Tomi Leino в Москве, весна 2004',
        'slug': 'tomi-leino-moscow-spring-2004',
        'description': 'Tomi Leino (Финляндия) выступает в Москве, весна 2004.',
    },
    '04Summer/RGtB': {
        'canonical_date': '2004-07-17',
        'clean_title': 'Russia Gets the Blues, клуб B.B.King, 17 июля 2004',
        'slug': 'russia-gets-the-blues-2004-07-17',
        'description': 'Russia Gets the Blues в клубе B.B.King, Москва, 17 июля 2004.',
    },
    '04Summer/Smith': {
        'canonical_date': '2004-07',
        'clean_title': 'J.C. Smith в Москве, лето 2004',
        'slug': 'jc-smith-moscow-summer-2004',
        'description': 'J.C. Smith выступает в Москве, лето 2004.',
    },
    '04Winter': {
        'canonical_date': '2004-01',
        'clean_title': 'Блюз-новости зимы 2004',
        'slug': 'blues-news-winter-2004',
        'description': 'ATB Blues News, зима 2004.',
    },

    # --- Year 2005 ---
    '05Fall': {
        'canonical_date': '2005-10',
        'clean_title': 'Блюз-новости осени 2005',
        'slug': 'blues-news-autumn-2005',
        'description': 'ATB Blues News, осень 2005.',
    },
    '05Spring/02Ragtime': {
        'canonical_date': '2005-03',
        'clean_title': 'Ragtime в Москве, весна 2005',
        'slug': 'ragtime-moscow-spring-2005',
        'description': 'Группа Ragtime (Нальчик) выступает в Москве, весна 2005.',
    },
    '05Spring/Broz': {
        'canonical_date': '2005-05-15',
        'clean_title': 'Bob Brozman в «Доме у Дороги», 15 мая 2005',
        'slug': 'bob-brozman-dom-u-dorogi-2005-05-15',
        'description': 'Американский гитарист Bob Brozman (Гавайи, блюз, мировая музыка) в клубе «Дом у Дороги», Москва, 15 мая 2005.',
    },
    '05Spring/Muddyjam': {
        'canonical_date': '2005-03',
        'clean_title': 'Muddy Waters Tribute Jam, весна 2005',
        'slug': 'muddy-waters-tribute-jam-2005',
        'description': 'Джем-сейшн памяти Muddy Waters, Москва, весна 2005.',
    },
    '05Spring/PeraJoe': {
        'canonical_date': '2005-03-31',
        'clean_title': 'Pera Joe & Friends в ЦДХ и «Доме у Дороги», 31 марта 2005',
        'slug': 'pera-joe-friends-2005-03-31',
        'description': 'Pera Joe (Белград) и Стан Станошевич в ЦДХ и клубе «Дом у Дороги», Москва, 31 марта 2005.',
    },
    '05Spring/buskbbking': {
        'canonical_date': '2005-04-23',
        'clean_title': 'Vidar Busk в клубе B.B.King, 23 апреля 2005',
        'slug': 'vidar-busk-bbking-2005-04-23',
        'description': 'Норвежский блюз-гитарист Vidar Busk и Eirik Bergene в клубе B.B.King, Москва, 23 апреля 2005.',
    },
    '05Spring/buskmon': {
        'canonical_date': '2005-04',
        'clean_title': 'Vidar Busk в понедельник, апрель 2005',
        'slug': 'vidar-busk-monday-april-2005',
        'description': 'Vidar Busk на блюзовом джеме в понедельник, апрель 2005.',
    },
    '05Spring/busksreda': {
        'canonical_date': '2005-04',
        'clean_title': 'Vidar Busk в среду, апрель 2005',
        'slug': 'vidar-busk-wednesday-april-2005',
        'description': 'Vidar Busk на блюзовом вечере в среду, апрель 2005.',
    },
    '05Summer': {
        'canonical_date': '2005-08-03',
        'clean_title': 'Scolder Bros. Blues Trio в «Доме у Дороги», 3 августа 2005',
        'slug': 'scolder-bros-dom-u-dorogi-2005-08-03',
        'description': 'Scolder Bros. Blues Trio в клубе «Дом у Дороги», Москва, 3 августа 2005.',
    },

    # --- Year 2007 ---
    '07Automn/Bonamassa07/content': {
        'canonical_date': '2007-10',
        'clean_title': 'Joe Bonamassa в Москве, октябрь 2007',
        'slug': 'joe-bonamassa-moscow-2007-10',
        'description': 'Joe Bonamassa выступает в Москве, осень 2007.',
    },
    '07Automn/Efes07/07efespress/content': {
        'canonical_date': '2007-09-02',
        'clean_title': 'Efes Blues Festival 2007 — пресс-конференция',
        'slug': 'efes-blues-festival-2007-press',
        'description': 'Пресс-конференция фестиваля Efes Blues Festival, 2 сентября 2007. Фото А. Евдокимова.',
    },
    '07Automn/Tail/content': {
        'canonical_date': '2007-10',
        'clean_title': 'Taildragger в Москве, осень 2007',
        'slug': 'taildragger-moscow-autumn-2007',
        'description': 'James Yancey «Taildragger» выступает в Москве, осень 2007.',
    },
    '07Automn/Tinderholt/content': {
        'canonical_date': '2007-10',
        'clean_title': 'Joakim Tinderholt в Москве, осень 2007',
        'slug': 'joakim-tinderholt-moscow-autumn-2007',
        'description': 'Joakim Tinderholt (Норвегия) выступает в Москве, осень 2007.',
    },
    '07Automn/baker/content': {
        'canonical_date': '2007-10',
        'clean_title': 'Lee Baker в Москве, осень 2007',
        'slug': 'lee-baker-moscow-autumn-2007',
        'description': 'Lee Baker выступает в Москве, осень 2007.',
    },
    '07Automn/ford/content': {
        'canonical_date': '2007-10',
        'clean_title': 'Robben Ford в Москве, осень 2007',
        'slug': 'robben-ford-moscow-autumn-2007',
        'description': 'Robben Ford выступает в Москве, осень 2007.',
    },
    '07Leto/DeltaNevi/dh/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Фестиваль «Дельта Невы» 2007, Санкт-Петербург',
        'slug': 'delta-nevy-festival-2007',
        'description': 'Фестиваль «Дельта Невы», Санкт-Петербург, 2007.',
    },
    '07Leto/GuyPhil/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Buddy Guy & Phil Upchurch в Москве, лето 2007',
        'slug': 'buddy-guy-phil-upchurch-moscow-2007',
        'description': 'Легендарный Buddy Guy и Phil Upchurch выступают в Москве, лето 2007.',
    },
    '07Leto/Holmi/Levina': {
        'canonical_date': '2007-07',
        'clean_title': 'Пустые Холмы — Левина, июль 2007',
        'slug': 'pustye-holmy-levina-2007-07',
        'description': 'Фото с фестиваля «Пустые Холмы», июль 2007.',
    },
    '07Leto/Holmi/evd': {
        'canonical_date': '2007-07-12',
        'clean_title': 'Пустые Холмы, 12 июля 2007',
        'slug': 'pustye-holmy-2007-07-12',
        'description': 'Фестиваль «Пустые Холмы», 12 июля 2007. Красивов, Русинов, Шомахов, Ринкевич. Фото А. Евдокимова.',
    },
    '07Leto/Lefortovo07/CO/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — CO',
        'slug': 'lefortovo-fest-2007-co',
        'description': 'Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Crossroadz/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Crossroadz',
        'slug': 'lefortovo-fest-2007-crossroadz',
        'description': 'Crossroadz на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/GS/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Gosha Shomakhov',
        'slug': 'lefortovo-fest-2007-gs',
        'description': 'Гоша Шомахов на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Greenday/GS/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Greenday / Shomakhov',
        'slug': 'lefortovo-fest-2007-greenday-gs',
        'description': 'Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Kiev/KBU/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Kiev Blues Union',
        'slug': 'lefortovo-fest-2007-kiev-blues-union',
        'description': 'Киевский блюз-юнион на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Majukov/OffBeat/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Мажуков / Offbeat',
        'slug': 'lefortovo-fest-2007-majukov-offbeat',
        'description': 'Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Petrovich/HRB/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Петрович / Hairiest Russian Blues',
        'slug': 'lefortovo-fest-2007-petrovich-hrb',
        'description': 'Петрович и Hairiest Russian Blues на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Popovic/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Ana Popovic',
        'slug': 'lefortovo-fest-2007-ana-popovic',
        'description': 'Сербская блюз-гитаристка Ana Popovic на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Shomahov/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Шомахов',
        'slug': 'lefortovo-fest-2007-shomakhov',
        'description': 'Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/Sobo/sobo/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Sobo',
        'slug': 'lefortovo-fest-2007-sobo',
        'description': 'Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/agranovski/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Аграновский',
        'slug': 'lefortovo-fest-2007-agranovski',
        'description': 'Dr. Аграновский на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Lefortovo07/fest/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo Open Air Blues Festival 2007',
        'slug': 'lefortovo-blues-fest-2007',
        'description': 'Lefortovo Open Air Blues Festival 2007, Москва. Фото А. Евдокимова.',
    },
    '07Leto/Lefortovo07/ford/content': {
        'canonical_date': '2007-07',
        'clean_title': 'Lefortovo 2007 — Robben Ford',
        'slug': 'lefortovo-fest-2007-robben-ford',
        'description': 'Robben Ford на Lefortovo Open Air Blues Festival 2007.',
    },
    '07Leto/Walz/content': {
        'canonical_date': '2007-06',
        'clean_title': 'Blues Walz 2007',
        'slug': 'blues-walz-2007',
        'description': 'Blues Walz, Москва, 2007.',
    },

    # --- Year 2008 ---
    '08Autumn/08Harpfest/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Московский Харп-Фестиваль 2008',
        'slug': 'harp-festival-moscow-2008',
        'description': 'Московский фестиваль губной гармоники, 2008.',
    },
    '08Autumn/BWconcert/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Bobby Watson концерт, осень 2008',
        'slug': 'blues-concert-autumn-2008',
        'description': 'Концерт, осень 2008.',
    },
    '08Autumn/BWdud/content': {
        'canonical_date': '2008-11',
        'clean_title': 'Вечер в «Доме у Дороги», осень 2008',
        'slug': 'dom-u-dorogi-autumn-2008',
        'description': 'Блюзовый вечер в клубе «Дом у Дороги», осень 2008.',
    },
    '08Autumn/BlueMonday/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Blue Monday, осень 2008',
        'slug': 'blue-monday-autumn-2008',
        'description': 'Blue Monday сессия, осень 2008.',
    },
    '08Autumn/Dunn0211/content': {
        'canonical_date': '2008-11-02',
        'clean_title': 'Duck Dunn в Москве, 2 ноября 2008',
        'slug': 'duck-dunn-moscow-2008-11-02',
        'description': 'Duck Dunn (бас-гитарист, Booker T. & the MGs, Blues Brothers) в Москве, 2 ноября 2008.',
    },
    '08Autumn/Dunn_08/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Duck Dunn в Москве, октябрь 2008',
        'slug': 'duck-dunn-moscow-october-2008',
        'description': 'Duck Dunn (Booker T. & the MGs) в Москве, осень 2008.',
    },
    '08Autumn/Efes/content': {
        'canonical_date': '2008-09',
        'clean_title': 'Efes Blues Festival 2008, Москва',
        'slug': 'efes-blues-festival-2008',
        'description': 'Efes Blues Festival 2008, Москва.',
    },
    '08Autumn/Ellis_08/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Tinsley Ellis в Москве, осень 2008',
        'slug': 'tinsley-ellis-moscow-autumn-2008',
        'description': 'Tinsley Ellis выступает в Москве, осень 2008.',
    },
    '08Autumn/Lefortovo/Lef_081/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo Blues Festival 2008',
        'slug': 'lefortovo-blues-fest-2008',
        'description': 'Lefortovo Open Air Blues Festival 2008, Москва.',
    },
    '08Autumn/Lefortovo/Q_Afterparty/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo 2008 — Afterparty',
        'slug': 'lefortovo-fest-2008-afterparty',
        'description': 'Afterparty Lefortovo Blues Festival 2008.',
    },
    '08Autumn/Lefortovo/Q_Jam/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo 2008 — Jam',
        'slug': 'lefortovo-fest-2008-jam',
        'description': 'Джем на Lefortovo Blues Festival 2008.',
    },
    '08Autumn/Lefortovo/Q_LilEd/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo 2008 — Lil\' Ed',
        'slug': 'lefortovo-fest-2008-lil-ed',
        'description': 'Lil\' Ed & the Blues Imperials на Lefortovo Blues Festival 2008.',
    },
    '08Autumn/Lefortovo/Q_Neal/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo 2008 — Kenny Neal',
        'slug': 'lefortovo-fest-2008-kenny-neal',
        'description': 'Kenny Neal на Lefortovo Blues Festival 2008.',
    },
    '08Autumn/Lefortovo/Q_Sardinas/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Lefortovo 2008 — Eric Sardinas',
        'slug': 'lefortovo-fest-2008-eric-sardinas',
        'description': 'Eric Sardinas на Lefortovo Blues Festival 2008.',
    },
    '08Autumn/Leino/content': {
        'canonical_date': '2008-09',
        'clean_title': 'Tomi Leino в Москве, осень 2008',
        'slug': 'tomi-leino-moscow-autumn-2008',
        'description': 'Tomi Leino (Финляндия) выступает в Москве, осень 2008.',
    },
    '08Autumn/MMB08/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Moscow Modern Blues, осень 2008',
        'slug': 'moscow-modern-blues-autumn-2008',
        'description': 'Moscow Modern Blues Band, осень 2008.',
    },
    '08Autumn/agr081121/content': {
        'canonical_date': '2008-11-21',
        'clean_title': 'Аграновский на сцене, 21 ноября 2008',
        'slug': 'agranovski-2008-11-21',
        'description': 'Dr. Аграновский на сцене, 21 ноября 2008.',
    },
    '08Autumn/bbking27/content': {
        'canonical_date': '2008-10-27',
        'clean_title': 'Вечер в клубе B.B.King, 27 октября 2008',
        'slug': 'bbking-27-october-2008',
        'description': 'Блюзовый вечер в клубе B.B.King, 27 октября 2008.',
    },
    '08Autumn/petrovich08/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Петрович, осень 2008',
        'slug': 'petrovich-autumn-2008',
        'description': 'Выступление Петровича, осень 2008.',
    },
    '08Autumn/sitin/content': {
        'canonical_date': '2008-10',
        'clean_title': 'Ситин, осень 2008',
        'slug': 'sitin-autumn-2008',
        'description': 'Выступление Ситина, осень 2008.',
    },
    '08Spring/AB_FBR/content': {
        'canonical_date': '2008-03',
        'clean_title': 'AB & Friends of Big Blues Revival, весна 2008',
        'slug': 'ab-friends-big-blues-revival-spring-2008',
        'description': 'Andrey Bratecki & Friends, Big Blues Revival, весна 2008.',
    },
    '08Spring/CDJ08_MT/content': {
        'canonical_date': '2008-04',
        'clean_title': 'ЦДЖ, весна 2008 — MT',
        'slug': 'cdj-2008-mt',
        'description': 'Центральный дом журналиста, весна 2008.',
    },
    '08Spring/JJM/content': {
        'canonical_date': '2008-04',
        'clean_title': 'JJ Milteau в Москве, весна 2008',
        'slug': 'jj-milteau-moscow-spring-2008',
        'description': 'JJ Milteau (Франция) выступает в Москве, весна 2008.',
    },
    '08Spring/cdj0819/content': {
        'canonical_date': '2008-04-19',
        'clean_title': 'ЦДЖ, 19 апреля 2008',
        'slug': 'cdj-19-april-2008',
        'description': 'Блюзовый вечер в Центральном доме журналиста, 19 апреля 2008.',
    },
    '08Spring/kav05/content': {
        'canonical_date': '2008-05',
        'clean_title': 'Юрий Каверкин, май 2008',
        'slug': 'kaverkin-may-2008',
        'description': 'Юрий Каверкин выступает в Москве, май 2008.',
    },
    '08Spring/posidelki08/content': {
        'canonical_date': '2008-03',
        'clean_title': 'Блюзовые посиделки, весна 2008',
        'slug': 'blues-posidelki-spring-2008',
        'description': 'Блюзовые посиделки, Москва, весна 2008.',
    },
    '08Spring/tr08/content': {
        'canonical_date': '2008-04',
        'clean_title': 'Трэйн-Рекордс, весна 2008',
        'slug': 'train-records-spring-2008',
        'description': 'Вечер в Train Records, весна 2008.',
    },
    '08Summer/08-07-25DUD/content': {
        'canonical_date': '2008-07-25',
        'clean_title': '«Дом у Дороги», 25 июля 2008',
        'slug': 'dom-u-dorogi-2008-07-25',
        'description': 'Блюзовый вечер в клубе «Дом у Дороги», 25 июля 2008.',
    },
    '08Summer/Veteran/content': {
        'canonical_date': '2008-07',
        'clean_title': 'The Veteran, лето 2008',
        'slug': 'veteran-summer-2008',
        'description': 'Блюзовый вечер в клубе «Ветеран», лето 2008.',
    },
    '08Summer/drnick/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Dr. Nick в Москве, лето 2008',
        'slug': 'dr-nick-moscow-summer-2008',
        'description': 'Dr. Nick выступает в Москве, лето 2008.',
    },
    '08Summer/us08/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Лето 2008',
        'slug': 'summer-2008',
        'description': 'Блюзовые вечера в Москве, лето 2008.',
    },
    '08Summer/usZ08/content': {
        'canonical_date': '2008-07',
        'clean_title': 'Лето 2008 (Z)',
        'slug': 'summer-2008-z',
        'description': 'Блюзовые вечера в Москве, лето 2008.',
    },
    '08Winter/08_Duarte/content': {
        'canonical_date': '2008-01',
        'clean_title': 'Chris Duarte в Москве, зима 2008',
        'slug': 'chris-duarte-moscow-winter-2008',
        'description': 'Chris Duarte выступает в Москве, зима 2008.',
    },
    '08Winter/08_Pera/content': {
        'canonical_date': '2008-02',
        'clean_title': 'Pera Joe в Москве, зима 2008',
        'slug': 'pera-joe-moscow-winter-2008',
        'description': 'Pera Joe (Белград) в Москве, зима 2008.',
    },
    '08Winter/BA_Moshkov0801/content': {
        'canonical_date': '2008-01',
        'clean_title': 'Андрей Братецкий — Мошков, январь 2008',
        'slug': 'bratecki-moshkov-january-2008',
        'description': 'Андрей Братецкий, январь 2008.',
    },
    '08Winter/MT_08_2/content': {
        'canonical_date': '2008-02',
        'clean_title': 'Moscow Blues, февраль 2008',
        'slug': 'moscow-blues-february-2008',
        'description': 'Блюзовый вечер в Москве, февраль 2008.',
    },
    '08Winter/agr081121/content': {
        'canonical_date': '2008-11-21',
        'clean_title': 'Аграновский, 21 ноября 2008',
        'slug': 'agranovski-november-2008',
        'description': 'Dr. Аграновский, ноябрь 2008.',
    },
    '08Winter/mt08/content': {
        'canonical_date': '2008-01',
        'clean_title': 'Moscow Blues, зима 2008',
        'slug': 'moscow-blues-winter-2008',
        'description': 'Блюзовые вечера в Москве, зима 2008.',
    },
    '08Winter/pera08/content': {
        'canonical_date': '2008-02',
        'clean_title': 'Pera Joe в Москве, февраль 2008',
        'slug': 'pera-joe-moscow-february-2008',
        'description': 'Pera Joe в Москве, февраль 2008.',
    },

    # --- Year 2009 ---
    '09Spring/090413/content': {
        'canonical_date': '2009-04-13',
        'clean_title': 'Блюзовый вечер, 13 апреля 2009',
        'slug': 'blues-evening-2009-04-13',
        'description': 'Блюзовый вечер, Москва, 13 апреля 2009.',
    },
    '09Spring/090517LT/content': {
        'canonical_date': '2009-05-17',
        'clean_title': 'Tomi Leino в Москве, 17 мая 2009',
        'slug': 'tomi-leino-moscow-2009-05-17',
        'description': 'Tomi Leino (Финляндия) в Москве, 17 мая 2009.',
    },
    '09Spring/09V_mm/content': {
        'canonical_date': '2009-05',
        'clean_title': 'Май 2009, Moscow Blues',
        'slug': 'moscow-blues-may-2009',
        'description': 'Блюзовые вечера в Москве, май 2009.',
    },
    '09Spring/BBR_X/content': {
        'canonical_date': '2009-04',
        'clean_title': 'Big Blues Revival X, 2009',
        'slug': 'big-blues-revival-x-2009',
        'description': 'Big Blues Revival, юбилейный концерт X, Москва, 2009.',
    },
    '09Spring/BC_BBK/content': {
        'canonical_date': '2009-04',
        'clean_title': 'Блюз-клуб B.B.King, весна 2009',
        'slug': 'bbking-spring-2009',
        'description': 'Блюзовые вечера в клубе B.B.King, весна 2009.',
    },
    '09Spring/BC_Dud/content': {
        'canonical_date': '2009-04',
        'clean_title': '«Дом у Дороги», весна 2009',
        'slug': 'dom-u-dorogi-spring-2009',
        'description': 'Вечера в клубе «Дом у Дороги», весна 2009.',
    },
    '09Spring/MM09': {
        'canonical_date': '2009-04',
        'clean_title': 'Moscow Modern Blues, весна 2009',
        'slug': 'moscow-modern-blues-spring-2009',
        'description': 'Moscow Modern Blues Band, весна 2009.',
    },
    '09Spring/MM09.old/content': {
        'canonical_date': '2009-04',
        'clean_title': 'Moscow Modern Blues, весна 2009 (архив)',
        'slug': 'moscow-modern-blues-spring-2009-old',
        'description': 'Moscow Modern Blues Band, весна 2009.',
    },
    '09Spring/wolf09/content': {
        'canonical_date': '2009-03',
        'clean_title': 'Wolf Mail в Москве, весна 2009',
        'slug': 'wolf-mail-moscow-spring-2009',
        'description': 'Wolf Mail выступает в Москве, весна 2009.',
    },
    '09Winter/WoodstockBlue': {
        'canonical_date': '2009-01',
        'clean_title': 'Woodstock Blue, зима 2009',
        'slug': 'woodstock-blue-winter-2009',
        'description': 'Woodstock Blue, Москва, зима 2009.',
    },
    '09Winter/harper/content': {
        'canonical_date': '2009-01',
        'clean_title': 'Ben Harper в Москве, зима 2009',
        'slug': 'ben-harper-moscow-winter-2009',
        'description': 'Ben Harper выступает в Москве, зима 2009.',
    },
    '09Winter/mud09/content': {
        'canonical_date': '2009-10-17',
        'clean_title': 'Mud Morganfield & Kingsize в Cotton Club, 17 октября 2009',
        'slug': 'mud-morganfield-cotton-club-2009-10-17',
        'description': 'Mud Morganfield (сын Muddy Waters) и Kingsize в Cotton Club, Москва, 17 октября 2009. Фото А. Евдокимова.',
    },
    '09Winter/offBeat/content': {
        'canonical_date': '2009-02',
        'clean_title': 'Offbeat, зима 2009',
        'slug': 'offbeat-winter-2009',
        'description': 'Offbeat Band, Москва, зима 2009.',
    },
    '09Winter/sugar/content': {
        'canonical_date': '2009-01',
        'clean_title': 'Sugar Blue в Москве, зима 2009',
        'slug': 'sugar-blue-moscow-winter-2009',
        'description': 'Sugar Blue (чикагский харпист) выступает в Москве, зима 2009.',
    },

    # --- Year 2010 ---
    '10Spring/10Bonamassa/content': {
        'canonical_date': '2010-04',
        'clean_title': 'Joe Bonamassa в Москве, апрель 2010',
        'slug': 'joe-bonamassa-moscow-april-2010',
        'description': 'Joe Bonamassa выступает в Москве, апрель 2010.',
    },
    '10Spring/10_03_Savoldelli': {
        'canonical_date': '2010-03',
        'clean_title': 'Paolo Savoldelli в Москве, март 2010',
        'slug': 'paolo-savoldelli-moscow-march-2010',
        'description': 'Paolo Savoldelli в Москве, март 2010.',
    },
    '10Spring/10_04_11BURDON': {
        'canonical_date': '2010-04-11',
        'clean_title': 'Eric Burdon в Москве, 11 апреля 2010',
        'slug': 'eric-burdon-moscow-2010-04-11',
        'description': 'Легендарный Eric Burdon (The Animals) выступает в Москве, 11 апреля 2010.',
    },
    '10Spring/10_04_18Tecora': {
        'canonical_date': '2010-04-18',
        'clean_title': 'Tocora, 18 апреля 2010',
        'slug': 'tocora-2010-04-18',
        'description': 'Tocora, Москва, 18 апреля 2010.',
    },
    '10Spring/28_III_2010WolfMail': {
        'canonical_date': '2010-03-28',
        'clean_title': 'Wolf Mail, 28 марта 2010',
        'slug': 'wolf-mail-2010-03-28',
        'description': 'Wolf Mail, Москва, 28 марта 2010.',
    },
    '10Spring/Billy_T_Band_at_Cotton_Club': {
        'canonical_date': '2010-04',
        'clean_title': 'Billy T Band в Cotton Club, весна 2010',
        'slug': 'billy-t-band-cotton-club-spring-2010',
        'description': 'Billy T Band в Cotton Club, Москва, весна 2010.',
    },
    '10Spring/Blues_Spinners': {
        'canonical_date': '2010-03',
        'clean_title': 'Blues Spinners, весна 2010',
        'slug': 'blues-spinners-spring-2010',
        'description': 'Blues Spinners, Москва, весна 2010.',
    },
    '10Spring/Castro': {
        'canonical_date': '2010-04',
        'clean_title': 'Tommy Castro в Москве, весна 2010',
        'slug': 'tommy-castro-moscow-spring-2010',
        'description': 'Tommy Castro выступает в Москве, весна 2010.',
    },
    '10Spring/Z_Star': {
        'canonical_date': '2010-04',
        'clean_title': 'Z Star, весна 2010',
        'slug': 'z-star-spring-2010',
        'description': 'Z Star, Москва, весна 2010.',
    },
    '10Spring/lazy/content': {
        'canonical_date': '2010-03',
        'clean_title': 'Lazy Lester в Москве, весна 2010',
        'slug': 'lazy-lester-moscow-spring-2010',
        'description': 'Lazy Lester (луизианский блюзмен) выступает в Москве, весна 2010.',
    },
    '10Summer/40AnniversaryUP': {
        'canonical_date': '2010-06',
        'clean_title': '40-летие Up, лето 2010',
        'slug': '40-anniversary-up-summer-2010',
        'description': '40-летний юбилей, Москва, лето 2010.',
    },
    '10Summer/BBMax2010': {
        'canonical_date': '2010-06',
        'clean_title': 'Big Blues Max, Москва, 2010',
        'slug': 'big-blues-max-2010',
        'description': 'Big Blues Max, Москва, лето 2010.',
    },
    '10Summer/Big_Blues_Revival': {
        'canonical_date': '2010-07',
        'clean_title': 'Big Blues Revival, лето 2010',
        'slug': 'big-blues-revival-summer-2010',
        'description': 'Big Blues Revival, Москва, лето 2010.',
    },
    '10Summer/Borny': {
        'canonical_date': '2010-06',
        'clean_title': 'Boney Fields в Москве, лето 2010',
        'slug': 'boney-fields-moscow-summer-2010',
        'description': 'Boney Fields выступает в Москве, лето 2010.',
    },
    '10Summer/DrNick01_11_10': {
        'canonical_date': '2010-11-01',
        'clean_title': 'Dr. Nick, 1 ноября 2010',
        'slug': 'dr-nick-2010-11-01',
        'description': 'Dr. Nick выступает в Москве, 1 ноября 2010.',
    },
    '10Summer/KWS10': {
        'canonical_date': '2010-07',
        'clean_title': 'Kenny Wayne Shepherd в Москве, 2010',
        'slug': 'kenny-wayne-shepherd-moscow-2010',
        'description': 'Kenny Wayne Shepherd выступает в Москве, лето 2010.',
    },
    '10Summer/Old_Guard': {
        'canonical_date': '2010-06',
        'clean_title': 'Old Guard Blues Band, лето 2010',
        'slug': 'old-guard-blues-band-summer-2010',
        'description': 'Old Guard Blues Band, Москва, лето 2010.',
    },
    '10Summer/Petrovich100605': {
        'canonical_date': '2010-06-05',
        'clean_title': 'Петрович, 5 июня 2010',
        'slug': 'petrovich-2010-06-05',
        'description': 'Петрович выступает, 5 июня 2010.',
    },
    '10Summer/Ppetrovich_40_years_on_scene': {
        'canonical_date': '2010-06',
        'clean_title': 'Петрович — 40 лет на сцене',
        'slug': 'petrovich-40-years-on-stage',
        'description': '40-летний юбилей на сцене Петровича, Москва, 2010.',
    },
    '10Summer/Robert_Lighthouse': {
        'canonical_date': '2010-06',
        'clean_title': 'Robert Lighthouse, лето 2010',
        'slug': 'robert-lighthouse-summer-2010',
        'description': 'Robert Lighthouse, Москва, лето 2010.',
    },

    # --- 2011 ---
    'svalbard/2013': {
        'canonical_date': '2013',
        'clean_title': 'Svalbard Blues Festival 2013',
        'slug': 'svalbard-blues-festival-2013',
        'description': 'Blues на Шпицбергене (Svalbard), 2013: Knut Reiersrud, Junior Watson, Raphael Wressnig, Mike Andersen, Teresa James, Anders Lewen, Sven Zetterberg.',
    },

    # --- Various ---
    'HarpFestV': {
        'canonical_date': '2004',
        'clean_title': 'V Московский Харп-Фестиваль',
        'slug': 'moscow-harp-festival-5',
        'description': 'V (пятый) Московский фестиваль губной гармоники. Фото А. Евдокимова.',
    },
    'JLWalker': {
        'canonical_date': '2003',
        'clean_title': 'Joe Louis Walker в Москве',
        'slug': 'joe-louis-walker-moscow',
        'description': 'Joe Louis Walker выступает в Москве.',
    },
    'Lamb2': {
        'canonical_date': '2004',
        'clean_title': 'Paul Lamb & the King Snakes в Москве (2)',
        'slug': 'paul-lamb-kingsnakes-moscow-2',
        'description': 'Paul Lamb & the King Snakes (Великобритания), Москва.',
    },
    'Pera': {
        'canonical_date': '2004',
        'clean_title': 'Pera Joe в Москве',
        'slug': 'pera-joe-moscow',
        'description': 'Pera Joe (Белград) выступает в Москве.',
    },
    'Kav16': {
        'canonical_date': '2015-11',
        'clean_title': 'Юрий Каверкин — интервью в «Доме у Дороги», ноябрь 2015',
        'slug': 'kaverkin-interview-november-2015',
        'description': 'Интервью с Юрием Каверкиным в клубе «Дом у Дороги», ноябрь 2015. Беседа Андрея Евдокимова.',
    },
    'DUD_v3': {
        'canonical_date': '2012',
        'clean_title': '«Дом у Дороги» v.3',
        'slug': 'dom-u-dorogi-v3',
        'description': 'Клуб «Дом у Дороги», третья версия клуба.',
    },
    'Kostin': {
        'canonical_date': '2003',
        'clean_title': 'Костин — портрет',
        'slug': 'kostin-portrait',
        'description': 'Фотографии музыканта Костина.',
    },
    'TailDragger2016/content': {
        'canonical_date': '2016',
        'clean_title': 'Taildragger в Москве, 2016',
        'slug': 'taildragger-moscow-2016',
        'description': 'James Yancey «Taildragger» выступает в Москве, 2016.',
    },
    '15Wayne': {
        'canonical_date': '2015',
        'clean_title': 'Kenny Wayne Shepherd в Москве, 2015',
        'slug': 'kenny-wayne-shepherd-moscow-2015',
        'description': 'Kenny Wayne Shepherd выступает в Москве, 2015.',
    },
    'puppy/content': {
        'canonical_date': '2007',
        'clean_title': 'Puppy — галерея',
        'slug': 'puppy-gallery',
        'description': 'Фотогалерея.',
    },
    '_12A': {
        'canonical_date': '2012',
        'clean_title': 'Блюзовые вечера в Москве, 2012',
        'slug': 'moscow-blues-2012',
        'description': 'Блюзовые вечера в Москве, 2012.',
    },
    '50Belov': {
        'canonical_date': '2012',
        'clean_title': '50-летие Белова',
        'slug': 'belov-50th-anniversary',
        'description': 'Юбилейный концерт — 50 лет Белова.',
    },
    '22_03_19_Kaverkin/content': {
        'canonical_date': '2022-03-19',
        'clean_title': 'Юрий Каверкин, 19 марта 2022',
        'slug': 'kaverkin-2022-03-19',
        'description': 'Юрий Каверкин выступает в Москве, 19 марта 2022.',
    },
    '14/14_02_12_Kaverkin_PeraJoe/content': {
        'canonical_date': '2014-02-12',
        'clean_title': 'Каверкин и Pera Joe, 12 февраля 2014',
        'slug': 'kaverkin-pera-joe-2014-02-12',
        'description': 'Юрий Каверкин и Pera Joe выступают в Москве, 12 февраля 2014.',
    },
}

# Season → approximate month mapping for date_from_season helper
SEASON_MONTH = {
    'Autumn': '10', 'Automn': '10', 'Winter': '01', 'Spring': '03', 'Summer': '07',
    'Leto': '07', 'Zima': '01',
}


def get_enrichment(path):
    """Get enrichment data for a gallery path."""
    return ENRICHMENT.get(path) or ENRICHMENT.get(f"'{path}'")


def build_canonical_date(path, existing_date):
    """Build canonical date from path and/or existing date field."""
    # Try from existing date string first
    cd = parse_date_from_str(existing_date)
    if cd:
        return cd

    # Try from path segments like YY_MM_DD
    cd = date_from_path(path)
    if cd:
        return cd

    # Fall back to year-only from path
    year = year_from_path(path)
    if year:
        # Try to get season from path
        top = path.split('/')[0]
        for season, month in SEASON_MONTH.items():
            if season in top:
                return f"{year}-{month}"
        return str(year)

    return None


def clean_title_from_existing(path, existing_title):
    """Clean up existing title if it's basically OK."""
    if not existing_title:
        return None
    # If title is just 'My Gallery', 'HF', 'My' — discard
    if existing_title.strip().lower() in ('my gallery', 'my', 'hf', ''):
        return None
    # If title > 120 chars, it's been corrupted by page dump
    if len(existing_title) > 120:
        # Take just first sentence
        t = existing_title[:120]
        # Cut at last word boundary before 120
        t = re.sub(r'\s\S+$', '', t)
        return t.strip()
    return existing_title.strip()


def make_slug_from_path(path):
    """Make a slug from path when no enrichment is available."""
    # Extract meaningful parts: date segments + last named segment
    parts = path.strip('/').split('/')
    cleaned = []
    for i, p in enumerate(parts):
        raw = p
        p = p.lstrip('_')
        # Skip 'content' suffix
        if p.lower() == 'content':
            continue
        # Skip top-level season/year-only components (e.g., _18, 04Spring, 07Leto)
        # These are just organizational prefixes, not meaningful title content
        if i == 0:
            # Pure 2-digit year (e.g., _18 → 18, _13 → 13)
            if re.match(r'^\d{2}$', p):
                continue
            # Season+year prefix (e.g., 04Spring, 07Leto, 09Winter)
            if re.match(r'^\d{2}[A-Z][a-z]+$', p) or re.match(r'^\d{2}[A-Z][a-zA-Z]+$', p):
                continue
        # Convert underscore dates like 13_02_16 or 18_07_08 to YYYY-MM-DD style
        m = re.match(r'^(\d{2})_(\d{2})_(\d{2})_?(.*)$', p)
        if m:
            yy, mm, dd, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            yyyy = 2000 + yy if yy <= 30 else 1900 + yy
            part = f"{yyyy}-{mm:02d}-{dd:02d}"
            if rest:
                part += '-' + slugify(rest)
            cleaned.append(part)
        else:
            cleaned.append(slugify(p))
    result = '-'.join(c for c in cleaned if c)
    return result[:80].strip('-')


def humanize_name(s):
    """Convert CamelCase or underscore_name to human-readable form."""
    # Split CamelCase
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
    # Replace underscores
    s = s.replace('_', ' ')
    # Collapse spaces
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# Map of known abbreviations/codes to readable names
KNOWN_CODES = {
    'DUD': 'Дом у Дороги',
    'BBK': 'B.B.King',
    'BBR': 'Big Blues Revival',
    'KW': 'Kenny Wayne Shepherd',
    'KWS': 'Kenny Wayne Shepherd',
    'KBBW': 'Kenny Wayne Shepherd Big Blues Band',
    'HRB': 'Hot Rod Band',
    'RH': 'Roadhouse',
    'SOBO': 'Sobo',
    'MBM': 'Moscow Blues Masters',
    'MMB': 'Moscow Modern Blues Band',
    'MMW': 'Medeski Martin & Wood',
    'JCS': 'J.C. Smith',
    'LL': 'Lil\' Louis',
    'RWIP': 'Roadhouse Blues Incorporated',
    'SKBB': 'South Kazakhstan Blues Band',
    'BG': 'Big Guy',
    'GS': 'Gosha Shomakhov',
    'TM': 'Tiomma',
    'MA': 'Mike Andersen',
}


def make_title_from_path(path, canonical_date):
    """Derive a human-readable title from a gallery path."""
    parts = [p for p in path.strip('/').split('/') if p.lower() not in ('content', 'images', 'photos')]

    # Skip pure year/season top-level components
    if parts and re.match(r'^_?\d{2}([A-Za-z].*)?$', parts[0]):
        parts = parts[1:]

    if not parts:
        return path

    # Take the last meaningful part
    last = parts[-1]

    # Strip YY_MM_DD prefix from last part
    m = re.match(r'^(\d{2})_(\d{2})_(\d{2})_?(.*)$', last)
    if m:
        yy, mm, dd, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        yyyy = 2000 + yy if yy <= 30 else 1900 + yy
        if rest:
            name = humanize_name(rest)
            # Expand known codes
            name = KNOWN_CODES.get(rest.upper(), name)
            return f"{name}, {dd:02d}.{mm:02d}.{yyyy}"
        else:
            return f"Блюзовый вечер, {dd:02d}.{mm:02d}.{yyyy}"

    # Strip YYYYMMDD prefix
    m = re.match(r'^(\d{4})(\d{2})(\d{2})(.*)$', last)
    if m:
        yyyy, mm, dd, rest = m.group(1), m.group(2), m.group(3), m.group(4).lstrip('_')
        if rest:
            name = humanize_name(rest)
            return f"{name}, {dd}.{mm}.{yyyy}"
        return f"Блюзовый вечер, {dd}.{mm}.{yyyy}"

    # Strip YY_MM_DD without trailing name
    m = re.match(r'^(\d{2})_(\d{2})_(\d{2})$', last)
    if m:
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        yyyy = 2000 + yy if yy <= 30 else 1900 + yy
        date_str = canonical_date or f"{yyyy}-{mm:02d}-{dd:02d}"
        return f"Блюзовый вечер, {dd:02d}.{mm:02d}.{yyyy}"

    # Check known codes
    code = last.upper().rstrip('0123456789').rstrip('_')
    if code in KNOWN_CODES:
        name = KNOWN_CODES[code]
        if canonical_date:
            return f"{name}, {canonical_date}"
        return name

    # General: humanize the last component
    name = humanize_name(last)
    if canonical_date and canonical_date not in name:
        return f"{name}, {canonical_date}"
    return name


def process_galleries():
    """Process all galleries and update their YAML files."""
    if not GALLERIES_YAML.exists():
        print("galleries.yaml not found")
        return

    content = GALLERIES_YAML.read_text(encoding='utf-8')
    import re as _re
    paths = _re.findall(r"^- path: (.+)$", content, _re.MULTILINE)

    updated = 0
    skipped = 0

    for raw_path in paths:
        # Handle quoted paths like '040416'
        path = raw_path.strip("'\"")

        slug_key = re.sub(r'[^a-z0-9]+', '-', path.lower()).strip('-')
        per_yaml = GALLERIES_DIR / f"{slug_key}.yaml"

        if not per_yaml.exists():
            skipped += 1
            continue

        data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}

        # Get enrichment
        enrich = get_enrichment(path)

        # Build canonical_date
        if enrich and enrich.get('canonical_date'):
            canonical_date = enrich['canonical_date']
        else:
            canonical_date = build_canonical_date(path, data.get('date') or '')

        # Build clean_title
        if enrich and enrich.get('clean_title'):
            clean_title = enrich['clean_title']
        else:
            clean_title = clean_title_from_existing(path, data.get('title') or '')
            if not clean_title:
                # Derive from path using smart rules
                clean_title = make_title_from_path(path, canonical_date or '')

        # Build slug
        if enrich and enrich.get('slug'):
            new_slug = enrich['slug']
        else:
            new_slug = make_slug_from_path(path)

        # Build description
        if enrich and enrich.get('description'):
            description = enrich['description']
        else:
            # Use existing extra_text if it's short enough (< 300 chars) and not junk
            et = data.get('extra_text') or ''
            if et and len(et) < 300 and et.strip().lower() not in ('my gallery', 'my', 'hf'):
                # Strip if it's just the title repeated
                lines = et.strip().split('\n')
                first = lines[0].strip() if lines else ''
                if first.lower() == clean_title.lower():
                    description = None
                else:
                    description = et[:200].strip()
            else:
                description = None

        # Determine if extra_text should be removed (it's a large article)
        et = data.get('extra_text') or ''
        extra_text_is_article = len(et) > 500

        # Write enrichment fields into the YAML data
        new_data = dict(data)
        new_data['canonical_date'] = canonical_date
        new_data['clean_title'] = clean_title
        new_data['slug'] = new_slug

        if description:
            new_data['description'] = description
        elif 'description' not in new_data:
            new_data['description'] = None

        if extra_text_is_article:
            # Move to a note field, clear from main
            new_data['extra_text'] = None  # cleared; original page has the article
            if 'source_article' not in new_data:
                new_data['source_article'] = None

        per_yaml.write_text(
            yaml.dump(new_data, allow_unicode=True, default_flow_style=False,
                      sort_keys=False, width=120),
            encoding='utf-8'
        )
        updated += 1

    print(f"Updated {updated} gallery YAML files, skipped {skipped}")


if __name__ == '__main__':
    process_galleries()
