"""Kontroly prepoctu skel Corona CT 70 AS -> Schuco LivIng MD.

Spustit:  python test_prevod_kusovniku.py
"""
import glob
import json
import os
import pathlib
from types import SimpleNamespace

import pytest

import prevod_kusovniku as p

ARCHIV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Archiv")


def test_cislo():
    assert p._cislo("1\xa0013,5") == 1013.5
    assert p._cislo("345,0") == 345.0


def test_fmt():
    assert p._fmt(1019.0) == r"1\'A0019,0"
    assert p._fmt(405.5) == "405,5"


def test_pozice_1_1():
    """Referencni hodnoty rucne overene proti katalogu a odsouhlasene zadavatelem."""
    el = p.nacti_element(glob.glob(ARCHIV + r"\*_1_1_22_6_12_55_56.rtf")[0])[0]
    p.prepocti(el)
    assert el.pozice == "1.1"
    assert [(s.sirka_nova, s.vyska_nova) for s in el.skla] == [(1019.0, 1125.0), (674.0, 1125.0)]


def test_stulp_a_pevne_zaskleni():
    """Pozice 4 = štulpové okno, pozice 3 = křídlo + pevné zasklení + křídlo."""
    el4 = p.nacti_element(glob.glob(ARCHIV + r"\*_4_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el4)
    assert [(s.sirka_nova, s.vyska_nova) for s in el4.skla] == [(405.5, 1115.0), (405.5, 1115.0)]

    el3 = p.nacti_element(glob.glob(ARCHIV + r"\*_3_22_6_12_55_54.rtf")[0])[0]
    p.prepocti(el3)
    assert [s.v_kridle for s in el3.skla] == [True, False, True]
    assert [(s.sirka_nova, s.vyska_nova) for s in el3.skla] == [
        (602.3, 1120.0), (722.3, 1216.0), (602.3, 1120.0)]


def test_vchodove_dvere_s_prahem():
    """Pozice 8 = vchodové dveře s prahem. Corona 147/107, LivIng 152/112.

    LivIng: křídlo 82/125 (19433) v rámu 80 -> w=47, x=152; práh = 105 + mezera 7.
    """
    el = p.nacti_element(glob.glob(ARCHIV + r"\*_8_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el)
    assert el.prah and [s.v_dverich for s in el.skla] == [True]
    assert [(s.sirka_nova, s.vyska_nova) for s in el.skla] == [(671.0, 1751.0)]
    assert not el.poznamky, el.poznamky


def test_okenni_kridlo_na_prahu():
    """Pozice 6 = okenní rám + vchodový práh. Dole Corona 70 (5+65), LivIng 68 (5+63)."""
    el = p.nacti_element(glob.glob(ARCHIV + r"\*_6_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el)
    assert "dole" not in el.ram_strany and p._na_prahu(el, "kridlo")
    assert [(s.sirka_nova, s.vyska_nova) for s in el.skla] == [(715.0, 1797.0)]
    assert not el.poznamky, el.poznamky


def test_rezne_delky_kridel():
    """Rezna delka kridla = sklo + 2x zasunuti + svar 6.

    Poz 1: sirka u sloupku roste o 1,5 (T-profil w 14,5 -> 13), vyska mezi ramy
    se nemeni (w 37 = 37). Poz 8: dvernich kridel se prevod nedotyka.
    """
    el1 = p.nacti_element(glob.glob(ARCHIV + r"\*_1_22_6_12_55_54.rtf")[0])[0]
    p.prepocti(el1)
    assert all(k.prepocteno for k in el1.kridla), el1.poznamky
    zmeny = {(k.fe, k.vodorovne): (k.rez, k.rez_novy) for k in el1.kridla}
    assert zmeny[("1", True)] == (804.5, 806.0)
    assert zmeny[("1", False)] == (1257.0, 1257.0)

    el8 = p.nacti_element(glob.glob(ARCHIV + r"\*_8_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el8)
    assert not any(k.prepocteno for k in el8.kridla)
    assert not el8.poznamky, el8.poznamky


def test_zapis_zvyrazni_sklo_i_kridlo(tmp_path):
    """Do RTF se zvyraznene zapisou nova skla i nove rezne delky kridel."""
    cesta = glob.glob(ARCHIV + r"\*_1_22_6_12_55_54.rtf")[0]
    el, raw, radky = p.nacti_element(cesta)
    p.prepocti(el)
    cil = str(tmp_path / "out.rtf")
    p.zapis_kusovnik(raw, radky, el, cil)

    text = open(cil, encoding="latin-1").read()
    assert p.ZVYRAZNI_ZAP + "674,0" in text                  # sklo 668,5 -> 674,0
    assert p.ZVYRAZNI_ZAP + "806,0" in text                  # kridlo 804,5 -> 806,0
    assert p.ZVYRAZNI_ZAP + r"1\'A0151,0" in text            # kridlo 1149,5 -> 1151,0
    assert "804,5" not in text                               # stara hodnota zmizela


def test_souhrn_skel_scita_shodne_rozmery():
    """Pozice 1 (4 ks) a 1.1 (2 ks) maji stejna skla -> po 6 kusu od kazdeho rozmeru."""
    elementy = []
    for vzor in (r"\*_1_22_6_12_55_54.rtf", r"\*_1_1_22_6_12_55_56.rtf"):
        el = p.nacti_element(glob.glob(ARCHIV + vzor)[0])[0]
        p.prepocti(el)
        elementy.append(el)

    radky, ks, m2 = p.souhrn_skel(elementy)
    assert ks == 12 and len(radky) == 2, radky
    assert [(r[2], r[3], r[4], r[6]) for r in radky] == [
        ("1019,0", "1125,0", 6, "1, 1.1"), ("674,0", "1125,0", 6, "1, 1.1")]
    assert round(m2, 3) == 11.428
    assert not any(r[-1] for r in radky)         # zadne "overit rucne"


def test_optimalizace_prepise_delky_kridel(tmp_path):
    """Nove rezne delky kridel se prepisou i v optimalizaci prirezu.

    804,5 je v souboru 12x -- 4 ks pozice 1 a 2 ks pozice 1.1, po dvou kusech.
    """
    p.spust(ARCHIV, str(tmp_path))
    text = open(tmp_path / "Optimalizace_přířezu_LivIng_MD.rtf", encoding="latin-1").read()
    assert text.count(p.ZVYRAZNI_ZAP + "806,0") == 12
    assert "804,5" not in text
    assert text.count(p.ZVYRAZNI_ZAP + r"1\'A0151,0") == 12   # 1 149,5 -> 1 151,0


def test_najdi_kusovniky():
    """Ve slozce najde jen kusovniky, ne sestavy a prehledy."""
    soubory = [os.path.basename(f) for f in p.najdi_kusovniky(ARCHIV)]
    assert len(soubory) == 10, soubory
    assert all("usovn" in s for s in soubory)
    assert not any("estava" in s for s in soubory)


def test_spust_jen_vybrane_soubory(tmp_path):
    """Prevest jde i podmnozinu kusovniku, ne jen celou slozku."""
    vybrane = p.najdi_kusovniky(ARCHIV)[:1]
    elementy, text = p.spust(ARCHIV, str(tmp_path), vybrane)
    assert len(elementy) == 1
    hotove = sorted(f.name for f in tmp_path.glob("Kusovník*.rtf"))
    assert hotove == [f"Kusovník_poz{elementy[0].pozice}_LivIng_MD.rtf"]
    # CSV se prepisuji jen vybranymi pozicemi, na to musi report upozornit
    assert "jen 1 z 10" in text



# --- okno -----------------------------------------------------------------
# Vzhled je ve web/, Python drzi jen Api. Testuje se tedy Api, ne widgety.


@pytest.fixture(autouse=True)
def nastaveni_v_tmp(tmp_path, monkeypatch):
    """Zadny test nesmi prepsat skutecne ulozeny rezim uzivatele."""
    import prevod_ui

    monkeypatch.setattr(prevod_ui, "NASTAVENI", str(tmp_path / "rezim"), raising=False)


@pytest.fixture
def api():
    import prevod_ui

    return prevod_ui.Api()


def cti_web(jmeno):
    return (pathlib.Path(__file__).parent / "web" / jmeno).read_text(encoding="utf-8")


def test_seznam_kusovniku(api):
    """Api nabidne kusovniky ze slozky i s pozici a rozmery."""
    polozky = api.seznam(ARCHIV)
    assert len(polozky) == 10
    assert [x["cesta"] for x in polozky] == p.najdi_kusovniky(ARCHIV)
    # jmena souboru z Macu jsou rozsypana, seznam proto ukazuje pozici a rozmery
    poz = {x["pozice"]: x for x in polozky}
    assert poz["2.1"]["rozmer"] == "550 × 845 mm" and poz["2.1"]["kus"] == 3


def test_seznam_neexistujici_slozky(api):
    """Po rozbaleni programu vedle nej Archiv nebyva -- nesmi to spadnout."""
    assert api.seznam(os.path.join("takova", "slozka", "neni")) == []


def test_drop_souboru(api):
    """Dropnute kusovniky se pridaji k seznamu a vrati se jako nove oznacene."""
    api.seznam(ARCHIV)
    vsechny = p.najdi_kusovniky(ARCHIV)

    odpoved = api.dropnuto(vsechny[:2])
    assert odpoved["nove"] == vsechny[:2]
    assert len(odpoved["seznam"]) == 10, "soubory ze slozky se nesmi duplikovat"


def test_drop_slozky_prepne_vstup(api):
    """Pretazena slozka se nastavi jako vstup a nacte se z ni seznam."""
    odpoved = api.dropnuto([ARCHIV])
    assert odpoved["vstup"] == os.path.normpath(ARCHIV)
    assert len(odpoved["seznam"]) == 10


def test_drop_jineho_souboru_rekne_proc(api):
    """Neco jineho nez .rtf ma dat hlasku, ne ticho."""
    odpoved = api.dropnuto([__file__])
    assert odpoved["nove"] == [] and "rtf" in odpoved["hlaska"].lower()


def test_prevest_jen_vybrane(api, tmp_path):
    """Prevadi se zaskrtnute kusovniky, ne cela slozka."""
    vybrane = p.najdi_kusovniky(ARCHIV)[:1]
    v = api.prevest(ARCHIV, str(tmp_path), vybrane)
    assert [f.name for f in tmp_path.glob("Kusovník*.rtf")] == ["Kusovník_poz1.1_LivIng_MD.rtf"]
    assert v["ks"] and v["radky"] and v["klic"] in ("ok", "", "varovna")


def test_prevest_bez_vyberu_neprevadi(api, tmp_path):
    """Bez zaskrtnuteho kusovniku se nic nedeje, jen se to rekne."""
    v = api.prevest(ARCHIV, str(tmp_path), [])
    assert v["klic"] == "varovna" and v["zalozka"] == "p-vyber"
    assert list(tmp_path.glob("*.rtf")) == []


def test_prevest_dropnute_bez_platneho_vstupu(api, tmp_path):
    """Po spusteni .exe vedle sebe Archiv nebyva -- dropnute soubory musi stacit."""
    api.seznam(str(tmp_path / "takova-slozka-neni"))
    dropnuty = p.najdi_kusovniky(ARCHIV)[1]
    api.dropnuto([dropnuty])
    v = api.prevest(str(tmp_path / "takova-slozka-neni"), str(tmp_path), [dropnuty])
    assert v["klic"] != "varovna", v["stav"]
    assert [f.name for f in tmp_path.glob("Kusovník*.rtf")] == ["Kusovník_poz1_LivIng_MD.rtf"]


def test_otevri_vystup(api, tmp_path, monkeypatch):
    """Existujici slozku otevre, jinak jen rekne."""
    import prevod_ui

    otevrene = []
    monkeypatch.setattr(prevod_ui.os, "startfile", otevrene.append, raising=False)
    monkeypatch.setattr(prevod_ui, "MAC", False)

    assert api.otevri(str(tmp_path))["ok"] and otevrene == [str(tmp_path)]
    v = api.otevri(str(tmp_path / "neexistuje"))
    assert not v["ok"] and v["hlaska"] and otevrene == [str(tmp_path)]


def test_otevri_vystup_na_macu(api, tmp_path, monkeypatch):
    """Na macOS os.startfile neexistuje, musi se pouzit 'open'."""
    import prevod_ui

    volane = []
    monkeypatch.setattr(prevod_ui, "MAC", True)
    monkeypatch.setattr(prevod_ui.subprocess, "run", lambda a, **k: volane.append(a))
    api.otevri(str(tmp_path))
    assert volane and volane[0][0] == "open"


def test_drop_dostane_plne_cesty(api):
    """Prohlizec zna jen jmena souboru; cestu dodava pywebview pres pywebviewFullPath.

    Kdyby se cetlo 'name' misto toho, prevod by dostal cesty bez adresare.
    """
    import prevod_ui

    class Udalost:
        def __init__(self): self.handlery = []
        def __iadd__(self, h): self.handlery.append(h); return self

    poslane = []
    udalost = Udalost()
    okno = SimpleNamespace(
        dom=SimpleNamespace(document=SimpleNamespace(events=SimpleNamespace(drop=udalost))),
        evaluate_js=poslane.append)
    prevod_ui._pripoj_drop(okno, api)
    assert okno.dom.document.events.drop.handlery, "drop se nikde neregistruje"

    soubor = p.najdi_kusovniky(ARCHIV)[0]
    okno.dom.document.events.drop.handlery[0].callback(
        {"dataTransfer": {"files": [{"name": os.path.basename(soubor),
                                     "pywebviewFullPath": soubor}]}})
    assert poslane and poslane[0].startswith("window.prijmiDropnute(")
    odpoved = json.loads(poslane[0][len("window.prijmiDropnute("):-1])
    assert odpoved["nove"] == [soubor], "do Pythonu nedosla plna cesta"
    assert api.soubory == [soubor]


def test_zapamatovany_rezim(tmp_path):
    """Rezim prezije restart; rozbite nebo nezapisovatelne nastaveni nesmi shodit okno."""
    import prevod_ui

    assert not prevod_ui._nacti_tmavy(), "bez souboru se startuje ve svetlem"
    prevod_ui._uloz_tmavy(True)
    assert prevod_ui._nacti_tmavy()
    prevod_ui._uloz_tmavy(False)
    assert not prevod_ui._nacti_tmavy()

    with open(prevod_ui.NASTAVENI, "w", encoding="utf-8") as f:
        f.write("nesmysl")
    assert not prevod_ui._nacti_tmavy(), "necekany obsah = svetly, ne vyjimka"

    prevod_ui.NASTAVENI = str(tmp_path / "neni" / "takova" / "slozka")
    prevod_ui._uloz_tmavy(True)                  # nezapisovatelna cesta se jen spolkne
    assert not prevod_ui._nacti_tmavy()


def test_zaklad_nese_rezim_i_odecet(api, monkeypatch):
    """Stranka dostane pri startu ulozeny rezim, at neblikne svetla a pak tmava."""
    import prevod_ui

    prevod_ui._uloz_tmavy(True)
    z = api.zaklad()
    assert z["tmavy"] is True
    assert [x[0] for x in z["odecet"]] == ["RÁM", "KŘÍDLO", "T-PROFIL", "ŠTULP b"]
    assert [x[1] for x in z["odecet"]] == [p.RAM_MM, p.KRIDLO_MM, p.T_PROFIL_MM, p.STULP_MM]


def test_ikony_slunce_a_mesic():
    """Prepinac je slunce/mesic; kazdy rezim ukazuje prave jednu ikonu."""
    html = cti_web("index.html")
    assert 'class="mesic"' in html and 'class="slunce"' in html
    assert 'html[data-rezim="svetly"] .slunce, html[data-rezim="tmavy"] .mesic { display: none; }'         in html, "ikony se neprepinaji podle rezimu"


def test_tmavy_rezim_ma_stejne_klice():
    """Chybejici promenna v tmave palete = prvek zustane ve svetle barve."""
    import re

    html = cti_web("index.html")
    def klice(vzor):
        blok = re.search(vzor, html, re.S).group(1)
        return set(re.findall(r"(--[a-z0-9-]+)\s*:", blok))

    svetla = klice(r":root \{(.*?)\}")
    tmava = klice(r'html\[data-rezim="tmavy"\] \{(.*?)\}')
    assert tmava, "tmava paleta chybi"
    assert tmava <= svetla, f"tmava definuje navic: {tmava - svetla}"
    barvy = {k for k in svetla if not k.startswith(("--okraj", "--mira", "--sloupec", "--tracking"))}
    assert barvy == tmava, f"tmave chybi: {barvy - tmava}"
