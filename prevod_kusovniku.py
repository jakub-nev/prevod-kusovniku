"""Převod kusovníků Corona CT 70 AS -> Schüco LivIng MD.

Načte kusovníky (.rtf), přepočte rozměry tabulí skla, zapíše nové kusovníky
se zvýrazněnými hodnotami a vyrobí seznam skel pro objednávku.

Použití:
    python prevod_kusovniku.py [vstupni_slozka] [vystupni_slozka]

Mění se rozměry skel, řezné délky křídel (okenních, balkonových i dveřních)
a boků rámu, který v LivIngu stojí na prahu, a to i v optimalizaci přířezu,
je-li ve složce. Odpočty se berou podle článku rámu, děliče a křídla (tabulka
PROFILY). Ostatní profily zůstávají původní (Corona) --
výztuže, zasklívačky a kování by potřebovaly artiklová data LivIng, která
v katalogu nejsou.

POZOR: v optimalizaci se přepisují jen délky kusů. Rozvržení po tyčích,
zbytkové délky ani prořez se nepřepočítávají -- po změně délek je potřeba
optimalizaci spustit znovu v programu, který ji vyrobil.
"""
import csv
import glob
import os
import re
import sys
from dataclasses import dataclass, field

# --- Odpočtové míry -------------------------------------------------------
# Profil se pozná podle článku Corony bez barvy (886616 -> 8866), LivIng je
# jeho náhrada. Odpočty se měří od reference: u rámu a prahu od vnější hrany
# prvku, u sloupku a štulpu od osy profilu.
#   w   = hrana křídla od reference
#   fix = hrana skla v pevném zasklení
#   zasunutí = sklo pod hranou křídla, tj. řezná délka křídla = sklo + 2*zasunutí + SVAR
#
# Corona CT 70 AS -- odvozeno z kusovníků samotných. Pevné zasklení v rámu 70/78
# v datech nebylo, 60 je podle řady AS LivIng (rám 70/80 = 50/60) a hlídá ho
# kontrola šířky. T-profil 70/110: w 24 z výkresu zakázky 230 poz 13 (pole 1030 =
# 47 + křídlo 959 + 24), fix 37 = w + 13 jako u T 70/91, v datech nebyl.
#
# Schüco LivIng MD -- katalog 09.2018 (5254_268666), str. 152-159, platí pro všechna křídla:
#   w: rám 70 = 37, rám 80 = 47, T-profil 92 = 13, T-profil 112 = 23, štulp b=74 = 4
#   fix MD: rám 70 = 52, rám 80 = 62, T-profil 92 = 28, T-profil 112 = 38
#   zasunutí = x - w: 63 (82/83, rám 70 x=100), 90 (82/110, x=127), 105 (82/125, x=142)
PROFILY = {"8865": ("rám 70/68", "19411 Blendrahmen 82/70"),
           "8864": ("dveřní rám 70/78", "19412 Blendrahmen 82/80"),
           "8869": ("T-profil 70/91", "19465 T-Profil 82/92"),
           "8848": ("T-profil 70/110", "19466 T-Profil 82/112"),
           "8636": ("štulp 70", "19472 Stulpprofil 74"),
           "8866": ("křídlo 70/83", "19431 Flügelrahmen 82/83"),
           "8563": ("balkonové křídlo 70/103", "19432 Flügelrahmen 82/110"),
           "8577": ("dveřní křídlo 70/118", "19433 Flügelrahmen 82/125")}
W = {"corona": {"8865": 37.0, "8864": 47.0, "8869": 14.5, "8848": 24.0, "8636": 4.2},
     "living": {"8865": 37.0, "8864": 47.0, "8869": 13.0, "8848": 23.0, "8636": 4.0}}
FIX = {"corona": {"8865": 50.0, "8864": 60.0, "8869": 27.5, "8848": 37.0, "8636": 47.2},
       "living": {"8865": 52.0, "8864": 62.0, "8869": 28.0, "8848": 38.0, "8636": 47.0}}
ZASUNUTI = {"corona": {"8866": 65.0, "8563": 85.0, "8577": 100.0},
            "living": {"8866": 63.0, "8563": 90.0, "8577": 105.0}}
# Křídlo bez spodního rámu (na prahu) končí mezeru nad spodní hranou prvku.
# Corona: 70/83 = 5 (zakázka 254 poz 6), 70/103 = 7 (230 poz 1), 70/118 = 7 (254 poz 8).
# LivIng mezeru přebírá -- katalog str. 194 dává u křídla 83 také 5, dveře nekótuje.
MEZERA = {"8866": 5.0, "8563": 7.0, "8577": 7.0}
# Balkonové dveře bez spodního rámu (SchüCal: "Balk. dveře ... bez rámu", křídlo
# 70/83 i 70/103) dostanou v LivIngu práh 25255500/600 a boky rámu stojí na něm.
# Katalog str. 115 dává práh 20 vysoký, 22 je z ruční opravy zadavatele
# (zakázka 230 poz 1: bok 2213 -> 2191).
PRAH_LIVING = 22.0

RAM_MM = "70 / 80"          # pohledové šířky LivIng, jen pro popisky
KRIDLO_MM = "83 / 110 / 125"
T_PROFIL_MM = 92
STULP_MM = 74

NEOVERENO = "NEPŘEPOČTENO - ověřit ručně"
SOUHRN_SLOUPCE = ["Typ skla", "Tl. [mm]", "Šířka [mm]", "Výška [mm]", "Kus",
                  "Plocha celkem [m2]", "Pozice", "Poznámka"]

SVAR = 6.0        # svarový přídavek: řezná délka = vnější míra + 6 (Corona i LivIng)
TOLERANCE = 5.0   # větší odchylka kontroly = prvek se nepřepočítává

BARVY = r"{\colortbl ;\red192\green0\blue0;\red255\green255\blue0;}"
ZVYRAZNI_ZAP, ZVYRAZNI_VYP = r"\cf1\highlight2 ", r" \highlight0\cf0 "


def _cislo(s):
    """'1 013,5' -> 1013.5 (nedělitelná mezera jako oddělovač tisíců)."""
    return float(s.replace("\xa0", "").replace(" ", "").replace(",", "."))


def _fmt(v):
    r"""1019.0 -> RTF řetězec 1\'A0019,0 (nedělitelná mezera jako v originálu)."""
    return f"{v:,.1f}".replace(",", "\x00").replace(".", ",").replace("\x00", r"\'A0")


@dataclass
class Sklo:
    fe: str
    typ_skla: str
    tloustka: str
    kus: int
    sirka: float
    vyska: float
    radek: int                                     # pořadí řádku v RTF
    kridlo: str = ""                               # článek křídla bez barvy, "" = pevné zasklení
    sirka_nova: float = 0.0
    vyska_nova: float = 0.0
    prepocteno: bool = False


@dataclass
class Kridlo:
    fe: str
    vodorovne: bool                                # dole/nahoře = šířka, jinak výška
    rez: float                                     # řezná délka v původním kusovníku
    radek: int
    rez_novy: float = 0.0
    prepocteno: bool = False


@dataclass
class BokRamu:
    cislo: str                                     # "Rám vpravo 2" -> "2", v optimalizaci "Bl 2"
    rez: float
    radek: int
    rez_novy: float = 0.0


@dataclass
class Element:
    soubor: str
    pozice: str = "?"
    system: str = ""
    kus: int = 1
    sirka: float = 0.0
    vyska: float = 0.0
    ram: str = ""                                  # článek rámu bez barvy
    boky: list = field(default_factory=list)       # svislé strany rámu (BokRamu)
    delice: list = field(default_factory=list)     # články sloupků a štulpů bez barvy
    ram_strany: set = field(default_factory=set)   # dole / nahoře / vpravo / vlevo
    prah: bool = False                              # dveřní práh místo spodního rámu
    ram_vyska: float = 0.0                         # vnější výška rámu bez podkladového profilu
    skla: list = field(default_factory=list)
    kridla: list = field(default_factory=list)     # profily křídla, jeden na stranu
    poznamky: list = field(default_factory=list)
    corona: bool = False                           # v okně ponecháno v Coroně, nepřevádí se


def _text(seg):
    """Holý text jedné buňky RTF."""
    s = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), seg)
    s = re.sub(r"\\'([0-9a-fA-F]{2})",
               lambda m: bytes([int(m.group(1), 16)]).decode("cp1250", "replace"), s)
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)
    return s.replace("{", "").replace("}", "").strip()


def nacti_element(cesta):
    """Vrací (Element, syrový RTF, řádky), řádky = [(začátek, konec, buňky)]."""
    raw = open(cesta, encoding="latin-1").read()
    el = Element(soubor=cesta)
    # Pozor: \cellx2027 je definice šířky sloupce, ne konec buňky -- dělit jen na
    # \cell, za kterým nenásleduje písmeno.
    radky = [(m.start(), m.end(),
              [_text(c) for c in re.split(r"\\cell(?![a-zA-Z])", m.group(0))[:-1]])
             for m in re.finditer(r"\{\\trowd.*?\\row\}", raw, re.S)]

    v_sklech, kridla_fe = False, {}
    for i, (_, _, b) in enumerate(radky):
        if any("Tabule skla" in c for c in b):
            v_sklech = True
            continue

        for j in range(len(b) - 1):                # hlavička ve tvaru "klíč: |hodnota|"
            k, v = b[j].rstrip(), b[j + 1]
            if k == "Číslo pozice:":
                el.pozice = v.strip()
            elif k == "Profilový systém:":
                el.system = v.strip()
            elif k == "Kus:":
                el.kus = int(_cislo(v))
            elif k == "Celková šířka:":
                el.sirka = _cislo(v.replace("mm", ""))
            elif k == "Celková výška:":
                el.vyska = _cislo(v.replace("mm", ""))

        if len(b) < 7 or not re.fullmatch(r"\d+", b[0]):
            continue

        if v_sklech:
            el.skla.append(Sklo(fe=b[4], typ_skla=b[2], tloustka=b[3], kus=int(_cislo(b[1])),
                                sirka=_cislo(b[5]), vyska=_cislo(b[6].lstrip("x ")), radek=i))
        else:
            nazev, mira = b[3], b[6]
            if nazev.startswith(("Křídlo", "Dveř")):   # druh křídla rozliší až článek
                kridla_fe[b[5]] = b[2][:4]
                if mira:
                    el.kridla.append(Kridlo(fe=b[5], rez=_cislo(mira), radek=i,
                                            vodorovne="dole" in nazev or "nahoře" in nazev))
            elif nazev.startswith(("Sloupek", "Stulp.profil")):
                el.delice.append(b[2][:4])
            elif "práh" in nazev.lower():
                el.prah = True
            elif nazev.startswith("Rám "):
                strana = nazev.split()[1]
                el.ram_strany.add(strana)
                el.ram = el.ram or b[2][:4]
                if strana in ("vpravo", "vlevo") and mira:
                    el.boky.append(BokRamu(nazev.split()[-1], _cislo(mira), i))

    if el.boky:
        el.ram_vyska = max(b.rez for b in el.boky) - SVAR
    for s in el.skla:
        s.kridlo = kridla_fe.get(s.fe, "")
    return el, raw, radky


def _na_prahu(el, sklo):
    """Pod křídlem je práh, ne rám: prvek má práh nebo nemá spodní rám."""
    return bool(sklo.kridlo) and (el.prah or "dole" not in el.ram_strany)


def _odpocet(soustava, el, sklo, strana):
    """Hrana skla od reference na straně `strana` (ram / prah / článek děliče)."""
    if strana == "ram":
        strana = el.ram
    if not sklo.kridlo:
        return FIX[soustava][strana]
    return ((MEZERA[sklo.kridlo] if strana == "prah" else W[soustava][strana])
            + ZASUNUTI[soustava][sklo.kridlo])


def _narust(el, sklo, strany):
    """O kolik sklo v LivIngu naroste: odpočty Corony minus odpočty LivIng."""
    return sum(_odpocet("corona", el, sklo, k) - _odpocet("living", el, sklo, k) for k in strany)


def _sousedi(el, index):
    """Typ souseda vlevo a vpravo pro pole `index`. Prvky jsou jednořadé."""
    delic = el.delice[0] if el.delice else ""
    if len(el.delice) == len(el.skla):             # jediné sklo vedle prázdného pole
        return ("ram", delic)
    return ("ram" if index == 0 else delic,
            "ram" if index == len(el.skla) - 1 else delic)


def prepocti_kridla(el):
    """Doplní křídla o nové řezné délky. Corona hodnotu nejdřív ověří."""
    sklo = {s.fe: s for s in el.skla}
    for k in el.kridla:
        s = sklo.get(k.fe)
        if not s or not s.prepocteno:
            continue
        stare, nove = (s.sirka, s.sirka_nova) if k.vodorovne else (s.vyska, s.vyska_nova)
        kontrola = stare + 2 * ZASUNUTI["corona"][s.kridlo] + SVAR
        if abs(kontrola - k.rez) > 0.5:
            el.poznamky.append(f"Fe {k.fe}: řezná délka křídla {k.rez:.1f} neodpovídá "
                               f"kontrole {kontrola:.1f} - křídlo nepřepočteno")
            continue
        k.rez_novy = round(nove + 2 * ZASUNUTI["living"][s.kridlo] + SVAR, 1)
        k.prepocteno = True


def _sedi_na_kridlo(el, sklo):
    """Corona sklo musí dát řezné délky svého křídla (sklo + 2*zasunutí + SVAR)."""
    rezy = [k for k in el.kridla if k.fe == sklo.fe]
    return bool(rezy) and all(
        abs((sklo.sirka if k.vodorovne else sklo.vyska)
            + 2 * ZASUNUTI["corona"][sklo.kridlo] + SVAR - k.rez) <= 0.5 for k in rezy)


def prepocti_boky(el):
    """Zkrátí boky rámu o práh LivIng. Corona bok jde až na zem: výška + pokos nahoře."""
    for b in el.boky:
        kontrola = el.vyska + SVAR / 2
        if abs(kontrola - b.rez) > 0.5:
            el.poznamky.append(f"rám {b.cislo}: řezná délka {b.rez:.1f} neodpovídá "
                               f"kontrole {kontrola:.1f} - bok nepřepočten")
            continue
        b.rez_novy = b.rez - PRAH_LIVING


def prepocti(el):
    """Doplní skla o nové rozměry. Při nesrovnalosti nechá rozměry beze změny."""
    if not el.skla:
        el.poznamky.append("prvek neobsahuje tabule skla")
        return el.skla
    if any(s.kridlo == "8577" for s in el.skla) and not el.prah:
        el.poznamky.append("dveřní křídlo bez prahu - odpočet spodní hrany neznámý, nepřepočteno")
        return el.skla
    if "Corona CT 70" not in el.system:
        el.poznamky.append(f"jiný profilový systém ({el.system}) - nepřepočteno")
        return el.skla
    neznamy = ({el.ram or "rám chybí"} | set(el.delice)
               | {s.kridlo for s in el.skla if s.kridlo}) - PROFILY.keys()
    if neznamy:
        el.poznamky.append(f"neznámý profil {', '.join(sorted(neznamy))} - nepřepočteno")
        return el.skla
    if len(set(el.delice)) > 1:
        el.poznamky.append("prvek míchá sloupky a štulpy - pořadí polí nelze určit")
        return el.skla
    prazdne_pole = len(el.delice) == len(el.skla) == 1     # druhé pole bez skla (průchod)
    if el.delice and len(el.delice) != len(el.skla) - 1 and not prazdne_pole:
        el.poznamky.append(f"děličů {len(el.delice)}, tabulí {len(el.skla)} - "
                           "prvek není jednořadý, nepřepočteno")
        return el.skla

    # Kontrola: stará skla složená s odpočty Corony musí dát celkovou šířku prvku.
    # Šířku prázdného pole kusovník nezná -- tam zbývá jen kontrola řezů křídla.
    soucet = 0.0
    for i, s in enumerate(el.skla):
        soucet += s.sirka + sum(_odpocet("corona", el, s, k) for k in _sousedi(el, i))
    odchylka = el.sirka - soucet
    if prazdne_pole:
        if not _sedi_na_kridlo(el, el.skla[0]):
            el.poznamky.append("pole bez skla a sklo nesedí na řezy křídla - NEPŘEPOČTENO")
            return el.skla
        el.poznamky.append("pole bez skla - kontrola šířky nejde, "
                           f"{'sloupek a práh zůstávají' if el.prah else 'sloupek zůstává'} "
                           "Corona - zkontrolovat ručně")
    elif abs(odchylka) > TOLERANCE:
        el.poznamky.append(f"kontrola šířky nesedí ({soucet:.1f} vs {el.sirka:.1f} mm, "
                           f"rozdíl {odchylka:+.1f}) - NEPŘEPOČTENO")
        return el.skla
    elif abs(odchylka) > 0.5:
        el.poznamky.append(f"kontrola šířky: rozdíl {odchylka:+.1f} mm (převzato beze změny)")

    for s in el.skla:
        if _na_prahu(el, s):                       # nahoře rám, dole práh
            d = el.vyska - (s.vyska + _odpocet("corona", el, s, "ram")
                            + _odpocet("corona", el, s, "prah"))
        elif {"dole", "nahoře"} <= el.ram_strany and el.ram_vyska:
            d = el.ram_vyska - (s.vyska + 2 * _odpocet("corona", el, s, "ram"))
        else:
            continue
        if abs(d) > 0.5:
            el.poznamky.append(f"Fe {s.fe}: kontrola výšky rozdíl {d:+.1f} mm")

    for i, s in enumerate(el.skla):
        dole = "prah" if _na_prahu(el, s) else "ram"
        s.sirka_nova = round(s.sirka + _narust(el, s, _sousedi(el, i)), 1)
        s.vyska_nova = round(s.vyska + _narust(el, s, ("ram", dole)), 1)
        s.prepocteno = True

    prepocti_kridla(el)
    if not el.prah and "dole" not in el.ram_strany and any(s.kridlo for s in el.skla):
        prepocti_boky(el)                          # balkonové dveře bez spodního rámu
    return el.skla


def _prepis_bunky(raw, radky, upravy, cil):
    """Kopie RTF se zvýrazněnými hodnotami. upravy = [(řádek, [(buňka, hodnota)])]."""
    novy = raw
    if "colortbl" not in novy:
        novy = novy.replace(r"{\rtf1 \ansi", r"{\rtf1 \ansi" + BARVY, 1)
    posun = len(novy) - len(raw)

    for radek, zmeny in sorted(upravy, key=lambda u: -u[0]):
        zac, kon, _ = radky[radek]
        zac, kon = zac + posun, kon + posun
        segmenty = re.split(r"(\\cell(?![a-zA-Z]))", novy[zac:kon])
        bunky = segmenty[::2]                       # liché položky jsou oddělovače
        for idx, hodnota in zmeny:
            m = re.search(r"\\q[lrc]\s+(.*?)\s*$", bunky[idx], re.S)
            if not m:
                raise ValueError(f"nerozpoznaná buňka: {bunky[idx]!r}")
            prefix = "x " if m.group(1).lstrip().startswith("x") else ""
            bunky[idx] = (bunky[idx][:m.start(1)] + ZVYRAZNI_ZAP + prefix + _fmt(hodnota)
                          + ZVYRAZNI_VYP + bunky[idx][m.end(1):])
        segmenty[::2] = bunky
        novy = novy[:zac] + "".join(segmenty) + novy[kon:]
    open(cil, "w", encoding="latin-1").write(novy)


def zapis_kusovnik(raw, radky, el, cil):
    """Zapíše kopii kusovníku se zvýrazněnými novými rozměry skel a řezy křídel."""
    upravy = [(s.radek, ((5, s.sirka_nova), (6, s.vyska_nova)))
              for s in el.skla if s.prepocteno]
    upravy += [(k.radek, ((6, k.rez_novy),)) for k in el.kridla
               if k.prepocteno and k.rez_novy != k.rez]   # shodu nemá smysl zvýrazňovat
    upravy += [(b.radek, ((6, b.rez_novy),)) for b in el.boky if b.rez_novy]
    _prepis_bunky(raw, radky, upravy, cil)


def _des(v, mist=1):
    """Desetinné číslo s čárkou, jak ho čeká Excel."""
    return f"{v:.{mist}f}".replace(".", ",")


def _rozmery(sklo):
    """Rozměry k objednání: přepočtené, u nepřepočtených původní."""
    return ((sklo.sirka_nova, sklo.vyska_nova) if sklo.prepocteno
            else (sklo.sirka, sklo.vyska))


def souhrn_skel(elementy):
    """Skla sečtená po shodných rozměrech pro objednávku: (řádky, kusů, m2)."""
    souhrn = {}
    for el in elementy:
        for s in el.skla:
            sir, vys = _rozmery(s)
            klic = (s.typ_skla, s.tloustka, round(sir, 1), round(vys, 1), el.corona)
            polozka = souhrn.setdefault(klic, {"kus": 0, "pozice": [], "overit": False})
            polozka["kus"] += s.kus
            polozka["overit"] |= not s.prepocteno and not el.corona
            if el.pozice not in polozka["pozice"]:
                polozka["pozice"].append(el.pozice)

    radky, celkem_ks, celkem_m2 = [], 0, 0.0
    for (typ, tl, sir, vys, corona), v in sorted(souhrn.items(), key=lambda x: (-x[0][2], -x[0][3])):
        plocha = sir * vys / 1e6 * v["kus"]
        celkem_ks += v["kus"]
        celkem_m2 += plocha
        radky.append([typ, tl, _des(sir), _des(vys), v["kus"], _des(plocha, 3),
                      ", ".join(v["pozice"]),
                      NEOVERENO if v["overit"] else "Corona" if corona else ""])
    return radky, celkem_ks, celkem_m2


def zapis_seznam_skel(elementy, slozka):
    """Dvě CSV: souhrn pro objednávku (sečteno po rozměrech) a podrobný rozpis."""
    podrobne = []
    for el in elementy:
        for s in el.skla:
            sir, vys = _rozmery(s)
            plocha = sir * vys / 1e6
            podrobne.append([el.pozice, s.fe, s.typ_skla, s.tloustka,
                             _des(sir), _des(vys), s.kus, _des(plocha, 3),
                             _des(plocha * s.kus, 3),
                             "" if s.prepocteno else "Corona" if el.corona else NEOVERENO])

    zamcene = []

    def uloz(nazev, hlavicka, radky):
        try:                                       # soubor bývá otevřený v Excelu
            with open(os.path.join(slozka, nazev), "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(hlavicka)
                w.writerows(radky)
        except PermissionError:
            zamcene.append(nazev)

    uloz("skla_podrobne.csv",
         ["Pozice", "Fe. Nr.", "Typ skla", "Tl. [mm]", "Šířka [mm]", "Výška [mm]",
          "Kus", "Plocha/ks [m2]", "Plocha celkem [m2]", "Poznámka"], podrobne)

    radky, celkem_ks, celkem_m2 = souhrn_skel(elementy)
    radky = radky + [[], ["CELKEM", "", "", "", celkem_ks, _des(celkem_m2, 3), "", ""]]
    uloz("skla_objednavka.csv", SOUHRN_SLOUPCE, radky)
    return celkem_ks, celkem_m2, zamcene


def najdi_kusovniky(slozka):
    """Kusovníky ve složce -- bez sestav, přehledů a optimalizací řezu."""
    return sorted(f for f in glob.glob(os.path.join(slozka, "*.rtf"))
                  if "usovn" in os.path.basename(f) and "estava" not in os.path.basename(f))


def spust(vstup, vystup, soubory=None, corona=()):
    """Převede kusovníky ze složky, nebo jen ty vyjmenované v `soubory`.

    Kusovníky v `corona` se nepřevádí: zkopírují se a jejich skla jdou do objednávky
    v původních rozměrech.
    """
    corona = {os.path.normpath(c) for c in corona}
    os.makedirs(vystup, exist_ok=True)
    elementy, zprava = [], []
    ve_slozce = najdi_kusovniky(vstup)
    soubory = ve_slozce if soubory is None else sorted(soubory)
    zprava.append(f"Corona CT 70 AS  ->  Schüco LivIng MD "
                  f"(rám {RAM_MM}, křídlo {KRIDLO_MM}, T-profil {T_PROFIL_MM}, "
                  f"štulp b={STULP_MM} mm)")
    zprava.append("")
    necitelne = []
    for cesta in soubory:
        el, raw, radky = nacti_element(cesta)
        elementy.append(el)
        if el.pozice == "?":                       # Word při uložení přepíše tabulky
            necitelne.append(os.path.basename(cesta))
            el.poznamky.append("NEPŘEČTEN - není to kusovník přímo ze SchuCalu (uložený "
                               "ve Wordu?), vyexportujte ho ze SchuCalu znovu")
            zprava += [f"Soubor {necitelne[-1]}", f"    ! {el.poznamky[-1]}"]
            continue
        el.corona = os.path.normpath(cesta) in corona
        if not el.corona:
            prepocti(el)
        cil = os.path.join(vystup, f"Kusovník_poz{el.pozice}_"
                                   f"{'Corona' if el.corona else 'LivIng_MD'}.rtf")
        try:
            zapis_kusovnik(raw, radky, el, cil)
        except PermissionError:                    # soubor bývá otevřený ve Wordu
            el.poznamky.append(f"soubor {os.path.basename(cil)} je zamčený (otevřený "
                               "v jiném programu) - NEZAPSÁN, zavři ho a spusť znovu")

        zprava.append(f"Pozice {el.pozice}  ({el.kus} ks, {el.sirka:.0f} x {el.vyska:.0f} mm)"
                      f"  ->  {os.path.basename(cil)}")
        if el.corona:
            zprava.append("    zůstává Corona CT 70 AS, nepřevádí se")
        elif any(s.prepocteno for s in el.skla):     # tj. profily jsou v tabulkách
            clanky = dict.fromkeys([el.ram] + el.delice + [s.kridlo for s in el.skla if s.kridlo])
            zprava.append("    " + ", ".join(" -> ".join(PROFILY[c]) for c in clanky))
        for s in el.skla:
            zmena = (f"{s.sirka_nova:>7.1f} x {s.vyska_nova:>7.1f}"
                     f"   ({PROFILY[s.kridlo][0] if s.kridlo else 'fix'})"
                     if s.prepocteno else "BEZE ZMĚNY")
            zprava.append(f"    Fe {s.fe:<4} {s.sirka:>7.1f} x {s.vyska:>7.1f}  ->  {zmena}")
        zmeny_kridel = {}                          # dole a nahoře mají stejnou délku
        for k in el.kridla:
            if k.prepocteno and k.rez_novy != k.rez:
                klic = (k.fe, k.vodorovne, k.rez, k.rez_novy)
                zmeny_kridel[klic] = zmeny_kridel.get(klic, 0) + 1
        for (fe, vodorovne, rez, rez_novy), ks in zmeny_kridel.items():
            zprava.append(f"    křídlo Fe {fe:<4} {'šířka' if vodorovne else 'výška'}"
                          f" {ks}x  {rez:>7.1f}  ->  {rez_novy:>7.1f}")
        boky = [(b.rez, b.rez_novy) for b in el.boky if b.rez_novy]
        for rez, rez_novy in dict.fromkeys(boky):
            zprava.append(f"    rám boky {boky.count((rez, rez_novy))}x  {rez:>7.1f}  ->  "
                          f"{rez_novy:>7.1f}   (práh LivIng 25255500/600)")
        zprava += [f"    ! {p}" for p in el.poznamky]

    optimalizace = [f for f in glob.glob(os.path.join(vstup, "*.rtf"))
                    if "ptimalizace" in os.path.basename(f)]
    if optimalizace:
        # Křídlo se páruje přes pozici, Fe a orientaci; části -1 a -3 jsou vodorovné
        # a mají shodnou délku, stejně tak -2 a -4 svislé. Bok rámu přes pozici
        # a popisek Bl 2 / Bl 4 (číslo strany jako v kusovníku).
        nove = {(el.pozice, k.fe, k.vodorovne): k.rez_novy
                for el in elementy for k in el.kridla
                if k.prepocteno and k.rez_novy != k.rez}
        nove.update({(el.pozice, f"Bl {b.cislo}"): b.rez_novy
                     for el in elementy for b in el.boky if b.rez_novy})
        raw = open(optimalizace[0], encoding="latin-1").read()
        radky = [(m.start(), m.end(),
                  [_text(c) for c in re.split(r"\\cell(?![a-zA-Z])", m.group(0))[:-1]])
                 for m in re.finditer(r"\{\\trowd.*?\\row\}", raw, re.S)]
        upravy = []
        for i, (_, _, b) in enumerate(radky):
            if not b or b[0] != "1" or i + 3 >= len(radky):
                continue                           # řádek délek, pod ním úhly/pozice/popisky
            pozice, popisky = radky[i + 2][2], radky[i + 3][2]
            zmeny = []
            for j in range(1, min(len(b), len(pozice), len(popisky))):
                if popisky[j].startswith(("Fl ", "Tr ")):    # okenní / dveřní křídlo
                    fe, _, cast = popisky[j][3:].rpartition("-")
                    klic = (pozice[j], fe, int(cast) % 2 == 1)
                else:                                    # bok rámu
                    klic = (pozice[j], popisky[j])
                if klic in nove:
                    zmeny.append((j, nove[klic]))
            if zmeny:
                upravy.append((i, zmeny))
        _prepis_bunky(raw, radky, upravy,
                      os.path.join(vystup, "Optimalizace_přířezu_LivIng_MD.rtf"))
        zprava.append(f"\nOptimalizace přířezu: přepsáno "
                      f"{sum(len(z) for _, z in upravy)} řezných délek křídel a rámů "
                      "-> Optimalizace_přířezu_LivIng_MD.rtf")

    ks, m2, zamcene = zapis_seznam_skel(elementy, vystup)
    zprava += ["", f"Celkem {ks} tabulí, {m2:.3f} m2  ->  "
                   "skla_objednavka.csv + skla_podrobne.csv"]
    for nazev in zamcene:
        zprava.append(f"POZOR - {nazev} je zamčený (otevřený v jiném programu) - NEZAPSÁN")
    if len(soubory) < len(ve_slozce):              # CSV nesou jen převedené pozice
        zprava.append(f"POZOR - převedeno jen {len(soubory)} z {len(ve_slozce)} kusovníků "
                      "ve složce, CSV proto obsahují jen tyto pozice")
    nedodelky = [el.pozice for el in elementy
                 if not el.corona and any(not s.prepocteno for s in el.skla)]
    if nedodelky:
        zprava.append(f"POZOR - nepřepočteno: pozice {', '.join(nedodelky)}")
    if necitelne:
        zprava.append(f"POZOR - nepřečteno, chybí v CSV: {', '.join(necitelne)}")

    text = "\n".join(zprava)
    open(os.path.join(vystup, "prevod_report.txt"), "w", encoding="utf-8").write(text)
    return elementy, text


if __name__ == "__main__":
    zde = os.path.dirname(os.path.abspath(__file__))
    print(spust(sys.argv[1] if len(sys.argv) > 1 else os.path.join(zde, "Archiv"),
                sys.argv[2] if len(sys.argv) > 2 else os.path.join(zde, "LivIng_MD"))[1])











