"""Převod kusovníků Corona CT 70 AS -> Schüco LivIng MD.

Načte kusovníky (.rtf), přepočte rozměry tabulí skla, zapíše nové kusovníky
se zvýrazněnými hodnotami a vyrobí seznam skel pro objednávku.

Použití:
    python prevod_kusovniku.py [vstupni_slozka] [vystupni_slozka]

Mění se POUZE rozměry skel. Řezné délky profilů zůstávají původní (Corona) --
ty potřebují svarové přídavky LivIng, ne přepočet odpočtových měr.
"""
import csv
import glob
import os
import re
import sys
from dataclasses import dataclass, field

# --- Odpočtové míry -------------------------------------------------------
# Vzdálenost hrany skla od reference: u rámu od vnější hrany prvku,
# u sloupku a štulpu od osy profilu.
#
# Corona CT 70 AS -- odvozeno z kusovníků samotných:
#   sklo v křídle = řezná délka křídla - 136, tj. w + 65
#   w = 37 (rám), 14,5 (sloupek), 4,2 (štulp);  sklo přímo v rámu = 50
#
# Schüco LivIng MD -- katalog 76666/02.2019, str. 153-161, sloupec křídlo 83 mm:
#   křídlo: rám x=100 (str. 154), T-profil 92 x=76 (str. 158), štulp b=74 x=67 (str. 161)
#   pevné zasklení: rám x=52 MD (str. 153), T-profil 92 x=28 MD (str. 157)
KRIDLO_MM = 83   # pohledová šířka křídla LivIng; při změně přepsat tabulku LIVING
RAM_MM = 70      # pohledová šířka rámu LivIng
T_PROFIL_MM = 92
STULP_MM = 74

CORONA = {"kridlo": {"ram": 102.0, "sloupek": 79.5, "stulp": 69.2,
                     # křídlo na vchodovém prahu: mezera 5 + 65 (ověřeno na pozici 6)
                     "prah": 70.0},
          "fix": {"ram": 50.0, "sloupek": 27.5, "stulp": 47.2},
          # dveře: rám 886416 w=47 + sklo 100 od hrany křídla; dole práh + mezera 7 + 100
          "dvere": {"ram": 147.0, "prah": 107.0}}
LIVING = {"kridlo": {"ram": 100.0, "sloupek": 76.0, "stulp": 67.0,
                     # křídlo 83 na dveřním prahu, str. 194: pohledová 88 = mezera 5 + křídlo 83
                     "prah": 68.0},
          "fix": {"ram": 52.0, "sloupek": 28.0, "stulp": 47.0},
          # dveře: řez Haustür 1:1 (str. 17) x=142; práh 25255500 (str. 116, výška 20 mm),
          # řez str. 194/195: celková pohledová 130 = mezera 5 + křídlo 125, sklo 130 - 20
          "dvere": {"ram": 142.0, "prah": 110.0}}

POPIS = {"kridlo": "křídlo", "fix": "fix", "dvere": "dveře"}

NEOVERENO = "NEPŘEPOČTENO - ověřit ručně"
SOUHRN_SLOUPCE = ["Typ skla", "Tl. [mm]", "Šířka [mm]", "Výška [mm]", "Kus",
                  "Plocha celkem [m2]", "Pozice", "Poznámka"]

SVAR = 6.0        # svarový přídavek Corona: řezná délka = vnější míra + 6
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
    v_kridle: bool = False
    v_dverich: bool = False
    sirka_nova: float = 0.0
    vyska_nova: float = 0.0
    prepocteno: bool = False


@dataclass
class Element:
    soubor: str
    pozice: str = "?"
    system: str = ""
    kus: int = 1
    sirka: float = 0.0
    vyska: float = 0.0
    delice: list = field(default_factory=list)     # 'sloupek' / 'stulp'
    ram_strany: set = field(default_factory=set)   # dole / nahoře / vpravo / vlevo
    prah: bool = False                              # dveřní práh místo spodního rámu
    ram_vyska: float = 0.0                         # vnější výška rámu bez podkladového profilu
    skla: list = field(default_factory=list)
    poznamky: list = field(default_factory=list)


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

    v_sklech, kridla_fe, dverni_fe, ram_rezy = False, set(), set(), []
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
            if nazev.startswith("Křídlo"):
                kridla_fe.add(b[5])
            elif nazev.startswith("Dveř"):        # dveřní křídlo má jiné odpočty než okenní
                dverni_fe.add(b[5])
            elif nazev.startswith("Sloupek"):
                el.delice.append("sloupek")
            elif nazev.startswith("Stulp.profil"):
                el.delice.append("stulp")
            elif "práh" in nazev.lower():
                el.prah = True
            elif nazev.startswith("Rám "):
                strana = nazev.split()[1]
                el.ram_strany.add(strana)
                if strana in ("vpravo", "vlevo") and mira:
                    ram_rezy.append(_cislo(mira))

    if ram_rezy:
        el.ram_vyska = max(ram_rezy) - SVAR
    for s in el.skla:
        s.v_kridle = s.fe in kridla_fe
        s.v_dverich = s.fe in dverni_fe
    return el, raw, radky


def _na_prahu(el, rezim):
    """Spodní hrana je dveřní práh, ne rám: prvek má práh nebo nemá spodní rám."""
    return rezim == "kridlo" and (el.prah or "dole" not in el.ram_strany)


def _rezim(sklo):
    return "dvere" if sklo.v_dverich else ("kridlo" if sklo.v_kridle else "fix")


def _sousedi(el, index):
    """Typ souseda vlevo a vpravo pro pole `index`. Prvky jsou jednořadé."""
    delic = el.delice[0] if el.delice else "sloupek"
    return ("ram" if index == 0 else delic,
            "ram" if index == len(el.skla) - 1 else delic)


def prepocti(el):
    """Doplní skla o nové rozměry. Při nesrovnalosti nechá rozměry beze změny."""
    if not el.skla:
        el.poznamky.append("prvek neobsahuje tabule skla")
        return el.skla
    if any(s.v_dverich for s in el.skla) and not el.prah:
        el.poznamky.append("dveřní křídlo bez prahu - odpočet spodní hrany neznámý, nepřepočteno")
        return el.skla
    if "Corona CT 70" not in el.system:
        el.poznamky.append(f"jiný profilový systém ({el.system}) - nepřepočteno")
        return el.skla
    if len(set(el.delice)) > 1:
        el.poznamky.append("prvek míchá sloupky a štulpy - pořadí polí nelze určit")
        return el.skla
    if el.delice and len(el.delice) != len(el.skla) - 1:
        el.poznamky.append(f"děličů {len(el.delice)}, tabulí {len(el.skla)} - "
                           "prvek není jednořadý, nepřepočteno")
        return el.skla

    # Kontrola: stará skla složená s odpočty Corony musí dát celkovou šířku prvku.
    soucet = 0.0
    for i, s in enumerate(el.skla):
        rezim = _rezim(s)
        vlevo, vpravo = _sousedi(el, i)
        soucet += s.sirka + CORONA[rezim][vlevo] + CORONA[rezim][vpravo]
    odchylka = el.sirka - soucet
    if abs(odchylka) > TOLERANCE:
        el.poznamky.append(f"kontrola šířky nesedí ({soucet:.1f} vs {el.sirka:.1f} mm, "
                           f"rozdíl {odchylka:+.1f}) - NEPŘEPOČTENO")
        return el.skla
    if abs(odchylka) > 0.5:
        el.poznamky.append(f"kontrola šířky: rozdíl {odchylka:+.1f} mm (převzato beze změny)")

    for s in el.skla:
        if _rezim(s) == "dvere" or _na_prahu(el, _rezim(s)):
            d = el.vyska - (s.vyska + CORONA[_rezim(s)]["ram"]
                            + CORONA[_rezim(s)]["prah"])   # nahoře rám, dole práh
        elif {"dole", "nahoře"} <= el.ram_strany and el.ram_vyska:
            d = el.ram_vyska - (s.vyska + 2 * CORONA[_rezim(s)]["ram"])
        else:
            continue
        if abs(d) > 0.5:
            el.poznamky.append(f"Fe {s.fe}: kontrola výšky rozdíl {d:+.1f} mm")

    for i, s in enumerate(el.skla):
        rezim = _rezim(s)
        vlevo, vpravo = _sousedi(el, i)
        s.sirka_nova = round(s.sirka + (CORONA[rezim][vlevo] - LIVING[rezim][vlevo])
                             + (CORONA[rezim][vpravo] - LIVING[rezim][vpravo]), 1)
        dole = "prah" if (rezim == "dvere" or _na_prahu(el, rezim)) else "ram"
        s.vyska_nova = round(s.vyska + (CORONA[rezim]["ram"] - LIVING[rezim]["ram"])
                             + (CORONA[rezim][dole] - LIVING[rezim][dole]), 1)
        s.prepocteno = True
    return el.skla


def zapis_kusovnik(raw, radky, skla, cil):
    """Zapíše kopii kusovníku, ve které jsou přepočtené rozměry skel zvýrazněné."""
    novy = raw
    if "colortbl" not in novy:
        novy = novy.replace(r"{\rtf1 \ansi", r"{\rtf1 \ansi" + BARVY, 1)
    posun = len(novy) - len(raw)

    for s in sorted((s for s in skla if s.prepocteno), key=lambda s: -s.radek):
        zac, kon, _ = radky[s.radek]
        zac, kon = zac + posun, kon + posun
        segmenty = re.split(r"(\\cell(?![a-zA-Z]))", novy[zac:kon])
        bunky = segmenty[::2]                       # liché položky jsou oddělovače
        for idx, hodnota in ((5, s.sirka_nova), (6, s.vyska_nova)):
            m = re.search(r"\\qr\s+(.*?)\s*$", bunky[idx], re.S)
            if not m:
                raise ValueError(f"nerozpoznaná buňka: {bunky[idx]!r}")
            prefix = "x " if m.group(1).lstrip().startswith("x") else ""
            bunky[idx] = (bunky[idx][:m.start(1)] + ZVYRAZNI_ZAP + prefix + _fmt(hodnota)
                          + ZVYRAZNI_VYP + bunky[idx][m.end(1):])
        segmenty[::2] = bunky
        novy = novy[:zac] + "".join(segmenty) + novy[kon:]
    open(cil, "w", encoding="latin-1").write(novy)


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
            klic = (s.typ_skla, s.tloustka, round(sir, 1), round(vys, 1))
            polozka = souhrn.setdefault(klic, {"kus": 0, "pozice": [], "overit": False})
            polozka["kus"] += s.kus
            polozka["overit"] |= not s.prepocteno
            if el.pozice not in polozka["pozice"]:
                polozka["pozice"].append(el.pozice)

    radky, celkem_ks, celkem_m2 = [], 0, 0.0
    for (typ, tl, sir, vys), v in sorted(souhrn.items(), key=lambda x: (-x[0][2], -x[0][3])):
        plocha = sir * vys / 1e6 * v["kus"]
        celkem_ks += v["kus"]
        celkem_m2 += plocha
        radky.append([typ, tl, _des(sir), _des(vys), v["kus"], _des(plocha, 3),
                      ", ".join(v["pozice"]), NEOVERENO if v["overit"] else ""])
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
                             "" if s.prepocteno else NEOVERENO])

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


def spust(vstup, vystup):
    os.makedirs(vystup, exist_ok=True)
    elementy, zprava = [], []
    soubory = sorted(f for f in glob.glob(os.path.join(vstup, "*.rtf"))
                     if "usovn" in os.path.basename(f) and "estava" not in os.path.basename(f))
    zprava.append(f"Corona CT 70 AS  ->  Schüco LivIng MD "
                  f"(rám {RAM_MM}, křídlo {KRIDLO_MM}, T-profil {T_PROFIL_MM}, "
                  f"štulp b={STULP_MM} mm)")
    zprava.append("")
    for cesta in soubory:
        el, raw, radky = nacti_element(cesta)
        prepocti(el)
        elementy.append(el)
        cil = os.path.join(vystup, f"Kusovník_poz{el.pozice}_LivIng_MD.rtf")
        try:
            zapis_kusovnik(raw, radky, el.skla, cil)
        except PermissionError:                    # soubor bývá otevřený ve Wordu
            el.poznamky.append(f"soubor {os.path.basename(cil)} je zamčený (otevřený "
                               "v jiném programu) - NEZAPSÁN, zavři ho a spusť znovu")

        zprava.append(f"Pozice {el.pozice}  ({el.kus} ks, {el.sirka:.0f} x {el.vyska:.0f} mm)"
                      f"  ->  {os.path.basename(cil)}")
        for s in el.skla:
            zmena = (f"{s.sirka_nova:>7.1f} x {s.vyska_nova:>7.1f}"
                     f"   ({POPIS[_rezim(s)]})"
                     if s.prepocteno else "BEZE ZMĚNY")
            zprava.append(f"    Fe {s.fe:<4} {s.sirka:>7.1f} x {s.vyska:>7.1f}  ->  {zmena}")
        zprava += [f"    ! {p}" for p in el.poznamky]

    ks, m2, zamcene = zapis_seznam_skel(elementy, vystup)
    zprava += ["", f"Celkem {ks} tabulí, {m2:.3f} m2  ->  "
                   "skla_objednavka.csv + skla_podrobne.csv"]
    for nazev in zamcene:
        zprava.append(f"POZOR - {nazev} je zamčený (otevřený v jiném programu) - NEZAPSÁN")
    nedodelky = [el.pozice for el in elementy if any(not s.prepocteno for s in el.skla)]
    if nedodelky:
        zprava.append(f"POZOR - nepřepočteno: pozice {', '.join(nedodelky)}")

    text = "\n".join(zprava)
    open(os.path.join(vystup, "prevod_report.txt"), "w", encoding="utf-8").write(text)
    return elementy, text


if __name__ == "__main__":
    print(spust(sys.argv[1] if len(sys.argv) > 1 else r"E:\Documents\odpočty\Archiv",
                sys.argv[2] if len(sys.argv) > 2 else r"E:\Documents\odpočty\LivIng_MD")[1])











