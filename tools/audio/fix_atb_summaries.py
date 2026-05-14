#!/usr/bin/env python3
"""One-off: rewrite ATB summaries from 'Выпуск посвящён X' to direct title style."""
import yaml
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
EPISODES_YAML = ARC / "data/atb/episodes.yaml"

REWRITES = {
    "atb-2014-03-14-deitra-farr":
        "Deitra Farr: гастроли по России; юбилеи Gay Adegbalola и Tony McPhee (Groundhogs)",
    "atb-2014-06-09-ian-siegal-peter-albin":
        "Ian Siegal: гастроли в Москве; 70-летие Peter Albin (Big Brother and the Holding Company)",
    "atb-2014-10-27-guy-davis":
        "Guy Davis — блюзмен, актёр и хранитель блюзовой традиции",
    "atb-2015-01-26-bob-stroger":
        "Bob Stroger: гастроли по России, январь 2015",
    "atb-2015-05-18-mccoy":
        "110-летие Kansas Joe McCoy, автора «Why Don't You Do Right»",
    "atb-2015-09-jimmy-reed":
        "90-летие Jimmy Reed — автора блюзовых стандартов из Чикаго",
    "atb-2015-10-12-kenny-blues-boss-wayne-part-1":
        "Kenny Blues Boss Wayne: гастроли по России; лауреаты Living Blues 2015",
    "atb-2015-10-12-kenny-blues-boss-wayne-part-2":
        "Kenny Blues Boss Wayne: биография, сотрудничество с Eric Bibb. Часть II",
    "atb-2015-10-26-willie-mabon":
        "90-летие Willie Mabon, автора «I'm Mad» и «The Seventh Son»",
    "atb-2015-11-09-bobby-rush":
        "Bobby Rush: биография, стиль, ключевые альбомы",
    "atb-2015-11-30-guy-davis":
        "Guy Davis: гастроли по России, 2015",
    "atb-2016-01-25-luther-tucker":
        "80-летие Luther Tucker; юбилеи Snooks Eaglin, Long John Baldry, Richie Havens",
    "atb-2016-02-29-sam-myers":
        "80-летие Sam Myers; юбилеи Irma Thomas и Bill Doggett",
    "atb-2016-03-21-pickett":
        "75-летие Wilson Pickett, 80-летие Solomon Burke — легенды соула 60-х",
    "atb-2016-04-04-harris":
        "Corey Harris: гастроли по России, апрель 2016",
    "atb-2016-04-25-ma-rainey":
        "120-летие Ma Rainey, «Матери блюза», и её «See See Rider»",
    "atb-2016-05-10-highway":
        "Фестиваль «61 Highway Blues Festival»: Коверкин, Аграновский, Ивашенко",
    "atb-2016-06-06-raful-neal":
        "Raful Neal — легенда луизианского блюза, мастер губной гармоники",
    "atb-2016-07-11-alligator":
        "45-летие Alligator Records; 33-й Чикагский блюз-фестиваль",
    "atb-2016-07-18-mack":
        "75-летие Lonnie Mack — памяти певца и гитариста, скончавшегося в 2016 году",
    "atb-2016-08-01-buddy-guy":
        "80-летие Buddy Guy — патриарха чикагского блюза",
    "atb-2016-08-08-buddy-guy":
        "80-летие Buddy Guy — патриарха чикагского блюза",
    "atb-2016-08-08-cannon":
        "Toronzo Cannon: дебют с альбомом «The Chicago Way» (2016)",
    "atb-2016-11-20-peter-green-memphis-horns-blues-boy-willie":
        "70-летие Peter Green, 75-летие Memphis Horns, 70-летие Blues Boy Willie",
    "atb-2016-11-27-rl-burnside-crossroads-80":
        "90-летие R.L. Burnside; 80 лет записи «Crossroads Blues» Robert Johnson",
    "atb-2016-12-04-sonny-boy-williamson":
        "Sonny Boy Williamson: записи для Trumpet и Chess — классика блюза",
    "atb-2016-12-11-larry-davis-guitar-slim-big-mama-thornton":
        "80-летие Larry Davis, 90-летие Guitar Slim, 90-летие Big Mama Thornton",
    "atb-2016-12-18-smoking-joe-kubek-bnois-king":
        "60-летие Smoking Joe Kubek и его дуэт с Bnois King",
    "atb-2016-12-25-big-mama-thornton-90":
        "90-летие Big Mama Thornton — певицы «Hound Dog» и «Ball and Chain»",
    "atb-2017-01-01-rolling-stones-blue-and-lonesome":
        "Rolling Stones «Blue and Lonesome» (2016): каверы Little Walter, Howlin' Wolf, Lightnin' Slim",
    "atb-2017-01-08-rolling-stones-blue-and-lonesome":
        "Rolling Stones «Blue and Lonesome» (2016): каверы Little Walter, Howlin' Wolf, Muddy Waters",
    "atb-2017-01-22-lucky-peterson-long-nights":
        "Lucky Peterson «Long Nights» (2016); The Hexman, Cedric James, Jeremy Spencer",
    "atb-2017-02-05-james-blood-ulmer-75":
        "75-летие James Blood Ulmer — гитариста, объединившего джаз, фанк и блюз",
    "atb-2017-02-12-james-blood-ulmer-75":
        "75-летие James Blood Ulmer — авангардного гитариста-вокалиста",
    "atb-2017-02-19-british-blues-invasion-russia":
        "«Британское ритм-блюзовое вторжение в Россию»: Matt Taylor, Gyles Robson, Julian Burdock",
    "atb-2017-02-26-grammy-blues-2017-bobby-rush":
        "Grammy 2017: Bobby Rush «Porcupine Meat»; Lurrie Bell, Luther Dickinson",
    "atb-2017-03-05-grammy-blues-2017":
        "Grammy 2017: Fantastic Negrito, Janiva Magness, Joe Louis Walker",
    "atb-2017-03-12-lucky-peterson-blues-2016":
        "Лучшие блюзовые альбомы 2016: Lucky Peterson, The Hexman, Jeremy Spencer",
    "atb-2017-03-19-blues-releases-2016":
        "Блюзовые новинки 2016: Mississippi Heat, Mike Zito, Rory Block, Big Bill Morganfield",
    "atb-2017-03-26-mississippi-heat-mike-zito-lucky-peterson":
        "Mississippi Heat, Mike Zito, Lucky Peterson, Rory Block, Andre Williams",
    "atb-2017-04-02-rolling-stones-blue-and-lonesome":
        "Rolling Stones «Blue and Lonesome»: оригиналы Little Walter, Howlin' Wolf, Eddie Taylor",
    "atb-2017-04-09-larry-davis-guitar-slim-big-mama-thornton":
        "80-летие Larry Davis, 90-летие Guitar Slim, 90-летие Big Mama Thornton",
    "atb-2017-04-16-sonny-boy-williamson-105":
        "105-летие Sonny Boy Williamson II — мастера блюзовой гармоники",
    "atb-2017-04-23-james-blood-ulmer-75":
        "75-летие James Blood Ulmer — авангардного джазово-блюзового гитариста",
    "atb-2017-04-30-ella-fitzgerald-100":
        "100-летие Ella Fitzgerald — «Первой леди джаза»",
    "atb-2017-05-07-joe-bonamassa-40":
        "40-летие Joe Bonamassa: от «Blues of Desperation» до «Concert at Carnegie Hall»",
    "atb-2017-05-08-joe-bonamassa":
        "40-летие Joe Bonamassa: «Blues of Desperation» и дискография",
    "atb-2017-05-14-taj-mahal-75":
        "75-летие Taj Mahal: альбом «TajMo» с Keb' Mo'",
    "atb-2017-05-21-kenny-blues-boss-wayne":
        "Kenny Blues Boss Wayne «Jumping and Bopping»; гастроли по России 2017",
    "atb-2017-05-28-lucky-lopez-barbara-dane":
        "80-летие Lucky Lopez, 90-летие Barbara Dane — певицы и активистки 1950-х",
    "atb-2017-06-04-otha-turner-110":
        "110-летие Otha Turner — мастера традиции Fife & Drum из Миссисипи",
    "atb-2017-06-11-kenny-wayne-shepherd-40":
        "40-летие Kenny Wayne Shepherd; Billy & DeDe Pierce, Toni Harper",
    "atb-2017-06-18-memphis-minnie-120":
        "120-летие Memphis Minnie — легендарной гитаристки и автора блюзовых стандартов",
    "atb-2017-06-25-delta-nevy-festival-2017":
        "13-й фестиваль «Дельта Невы»: Shana Waterstown, Blues Doctors, The Jumping Cats",
    "atb-2017-07-09-blind-boy-fuller-110":
        "110-летие Blind Boy Fuller — основателя пидмонтского блюзового стиля",
    "atb-2017-07-10-blind-boy-fuller":
        "110-летие Blind Boy Fuller — пионера пидмонтского блюза",
    "atb-2017-07-16-blind-boy-fuller-carlos-santana-70":
        "110-летие Blind Boy Fuller, 70-летие Carlos Santana",
    "atb-2017-07-23-lena-horne-eddie-floyd-buckwheat-zydeco":
        "80-летие Lena Horne, 80-летие Eddie Floyd, 60-летие лидера Buckwheat Zydeco",
    "atb-2017-07-30-cedell-davis-90":
        "90-летие CeDell Davis — мастера слайд-гитары с техникой игры кухонным ножом",
    "atb-2017-08-06-deitra-farr-rick-derringer-magic-slim":
        "70-летие Rick Derringer, 80-летие Magic Slim, 100-летие Mose Vinson; Deitra Farr",
    "atb-2017-08-08-blind-boy-fuller-110":
        "110-летие Blind Boy Fuller — пионера пидмонтского блюза",
    "atb-2017-09-25-cj-chenier":
        "60-летие C.J. Chenier; 90-летие George Mayweather",
    "atb-2017-10-02-chenier":
        "60-летие C.J. Chenier, 80-летие Joe Guitar Hughes; памяти Nick Curran",
    "atb-2018-01-15-corey-harris":
        "Corey Harris; 90-летие Ruth Brown: интервью и живые записи",
    "atb-2018-01-22-corey-harris":
        "Corey Harris: гастроли по России, январь–февраль 2018",
    "atb-2018-03-05-canned-heat":
        "Canned Heat; 75-летие Bob «Bear» Hite",
    "atb-2018-04-04-jimmy-nelson":
        "Юбилей Jimmy «T-99» Nelson; Shemekia Copeland, Tony McPhee, Gay Adegbalola, Luther Johnson",
    "atb-2018-04-18-gary-primich":
        "60-летие Gary Primich — виртуозного блюзового гармониста",
    "atb-2018-04-23-eddie-king":
        "80-летие Eddie King — чикагского гитариста из окружения Koko Taylor",
    "atb-2018-07-02-buddy-guy":
        "Buddy Guy «Blues Is Alive and Well» (2018): новый альбом накануне 82-летия",
    "atb-2018-08-06-margolin-wlc-i-moscow":
        "Bob Margolin и Welch-Ledbetter Connection: концерт в Москве, 7 августа 2018",
    "atb-2018-10-01-steve-miller":
        "Steve Miller; 70-летие Duke Robillard, 75-летие Roy Bookbinder, 110-летие Sammy Price",
    "atb-2018-10-22-burton":
        "Charles Burton: гастроли по России; 75-летие Corky Siegel",
    "atb-2019-02-25-harris":
        "50-летие Corey Harris — гитариста и исследователя африканских корней блюза",
    "atb-2019-04-15-bessie-smith":
        "125-летие Bessie Smith — жизнь, карьера и главные песни Императрицы блюза",
    "atb-2019-04-22-costello":
        "40-летие Sean Costello; 75-летие John Kay (Steppenwolf)",
    "atb-2019-05-06-campbell":
        "80-летие Eddie C. Campbell, 70-летие Bob Margolin — блюзмены круга Muddy Waters",
    "atb-2019-05-20-arkhangelsk":
        "14-й Архангельский блюз-фестиваль; юбилеи ZZ Top, Joe Cocker; памяти Lil' Dave Thompson",
    "atb-2019-06-17-bb-king-live":
        "BB King: от «Live at the Regal» (1964) до «BB King Live» (2008)",
    "atb-2019-06-24-beck":
        "75-летие Jeff Beck — от блюза к вершинам рок-музыки",
    "atb-2019-08-12-jb-lenoir-90":
        "90-летие J.B. Lenoir — автора политических блюзов, повлиявшего на весь жанр",
    "atb-2019-08-19-aretha":
        "Годовщина смерти Aretha Franklin: блюзовое наследие Королевы соула",
    "atb-2019-08-26-kenny-wayne-shepherd-bobby-rush":
        "Kenny Wayne Shepherd «Traveler», Bobby Rush «Sitting on Top of the Blues»; Kingfish Ingram",
    "atb-2019-09-02-bessie-smith":
        "Bessie Smith — Императрица блюза: главные записи 1920–30-х и история жизни",
    "atb-2019-09-09-tony-mcphee-groundhogs":
        "Tony McPhee и Groundhogs: связи с Muddy Waters, Howlin' Wolf, John Lee Hooker",
    "atb-2019-09-16-bb-king-ruth-brown-katie-webster":
        "B.B. King, Ruth Brown, Katie Webster — юбилеи сентября 2019",
    "atb-2019-09-23-bb-king-tribute-samantha-fish":
        "Трибьют памяти B.B. King; новинки Samantha Fish, переиздания Jesse Ed Davis",
    "atb-2019-09-30-otis-rush-holmes-brothers":
        "Памяти Otis Rush; юбилей Sherman Holmes (The Holmes Brothers)",
    "atb-2019-10-07-little-milton-85":
        "85-летие Little Milton; юбилеи Guitar Shorty, Snooky Pryor; памяти Deborah Coleman",
    "atb-2019-10-28-nappy-brown-ben-harper":
        "90-летие Nappy Brown, 50-летие Ben Harper; Charlie Musselwhite, Mavis Staples",
    "atb-2020-02-24-winter-blues":
        "70-летие George Thorogood, 100-летие Dave Bartholomew; гастроли JJ Thames",
    "atb-2020-04-06-muddy-waters-alberta-hunter":
        "105-летие Muddy Waters, 125-летие Alberta Hunter; апрельские юбиляры",
    "atb-2020-05-04-may-show":
        "110-летие Homesick James (30 апреля 1910)",
    "atb-2020-05-25-vidar-busk-peggy-lee":
        "50-летие Vidar Busk, 100-летие Peggy Lee; Scatman Crothers, Philadelphia Jerry Ricks",
    "atb-2020-06-22-bg":
        "Buddy Guy: 83-летие — жизнь во время пандемии и расовых протестов",
    "atb-2020-07-06-dylan":
        "Bob Dylan «Rough and Rowdy Ways»; Shirley King «Blues Freak King»; юбилей Fontella Bass",
    "atb-2020-09-30-tail-dragger-tiny-bradshaw":
        "Юбилеи Tiny Bradshaw, Fenton Robinson, Tail Dragger и других блюзменов",
    "atb-2021-05-31-may-show":
        "Robert Finley и The Black Keys: новые альбомы, май 2021",
    "atb-2021-07-26-lonnie-mack":
        "80-летие Lonnie Mack — гитарного героя начала 1960-х",
    "atb-2021-10-18-october-show":
        "110-летие Piano Red, 120-летие Adelaide Hall, 80-летие Steve Cropper",
    "atb-2021-10-25-green":
        "75-летие Peter Green — основателя Fleetwood Mac, британского блюзового гения",
    "atb-2022-01-17-chicago-blues":
        "90-летие Lester Davenport, 90-летие Barbara Lynn, 80-летие Whispering Smith",
}


def main():
    episodes = yaml.safe_load(EPISODES_YAML.read_text(encoding="utf-8")) or []
    changed = 0
    for ep in episodes:
        slug = ep.get("slug", "")
        if slug in REWRITES:
            ep["summary"] = REWRITES[slug]
            changed += 1
    EPISODES_YAML.write_text(
        yaml.dump(episodes, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"Updated {changed} summaries")


if __name__ == "__main__":
    main()
