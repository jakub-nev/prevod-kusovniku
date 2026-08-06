"""Kontroly prepoctu skel Corona CT 70 AS -> Schuco LivIng MD.

Spustit:  python test_prevod_kusovniku.py
"""
import glob
import os
from types import SimpleNamespace

import pytest

import prevod_kusovniku as p

ARCHIV = r"E:\Documents\odpočty\Archiv"


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


def test_otevri_vystup(tmp_path, monkeypatch):
    """Tlacitko 'Otevrit slozku s vysledky': existujici slozku otevre, jinak jen rekne."""
    import prevod_ui

    otevrene, hlasky = [], []
    monkeypatch.setattr(prevod_ui.os, "startfile", otevrene.append, raising=False)
    monkeypatch.setattr(prevod_ui.messagebox, "showinfo",
                        lambda *a, **k: hlasky.append(a))

    def okno(cesta):                             # duck-typed self, okno netreba stavet
        return SimpleNamespace(vystup=SimpleNamespace(get=lambda: cesta))

    prevod_ui.Okno.otevri_vystup(okno(str(tmp_path)))
    assert otevrene == [str(tmp_path)] and not hlasky

    prevod_ui.Okno.otevri_vystup(okno(str(tmp_path / "neexistuje")))
    assert otevrene == [str(tmp_path)] and len(hlasky) == 1


@pytest.fixture(scope="module")
def okno():
    """Jedno okno na vsechny UI testy -- druha tk.Tk() v jednom procesu je krehka."""
    import prevod_ui

    o = prevod_ui.Okno()
    o.withdraw()
    yield o
    o.destroy()


def test_vyber_kusovniku_v_okne(okno):
    """Okno nabidne kusovniky ze slozky, vsechny predvybrane; vyber jde zuzit."""
    okno.vstup.set(ARCHIV)                           # zmena slozky seznam prenacte sama
    assert okno.seznam.size() == 10
    assert len(okno.vybrane_soubory()) == 10

    okno.seznam.selection_clear(0, "end")
    okno.seznam.selection_set(2)
    assert okno.vybrane_soubory() == [okno.soubory[2]]
    # jmena souboru z Macu jsou rozsypana, seznam proto ukazuje pozici a rozmery
    assert okno.seznam.get(2).startswith("pozice 2.1")
    assert "550 × 845 mm" in okno.seznam.get(2)


def test_okno_ma_zapnuty_drop(okno):
    """Drop musi brat cele okno, ne jen seznam -- soubor lze pustit kamkoliv.

    Pozor: tkdnd::drop_target names vraci Tcl_Obj, ktery je pravdivy i kdyz
    je prazdny -- registrace se overuje pres <<Drop>> v bind().
    """
    import prevod_ui

    assert prevod_ui.DND_FILES, "tkinterdnd2 chybi, drag & drop by nefungoval"
    assert okno.dnd_aktivni
    for jmeno, widget in (("okno", okno), ("seznam", okno.seznam)):
        assert "<<Drop>>" in widget.bind(), f"{jmeno} neprijima drop"


def test_drop_ma_vizualni_odezvu(okno):
    """Pri pretazeni nad okno musi byt videt, ze se soubor prijme."""
    puvodni = okno.seznam.cget("background")
    okno._drag_enter()
    assert okno.seznam.cget("background") != puvodni, "seznam se pri pretazeni nezvyrazni"
    okno._drag_leave()
    assert okno.seznam.cget("background") == puvodni, "zvyrazneni po odejeti nezmizelo"


def test_drop_souboru_do_okna(okno):
    """Dropnute kusovniky se pridaji do seznamu a oznaci se.

    TkDnD posila cesty oddelene mezerou, ty s mezerou uvnitr ve slozenych
    zavorkach -- a cesty v Archivu mezery maji.
    """
    okno.vstup.set(ARCHIV)
    okno.seznam.selection_clear(0, "end")
    vsechny = p.najdi_kusovniky(ARCHIV)

    okno.pridej_dropnute(" ".join("{" + f + "}" for f in vsechny[:2]))
    assert sorted(okno.vybrane_soubory()) == sorted(vsechny[:2])

    okno.pridej_dropnute("{" + vsechny[5] + "}")     # druhy drop pridava k vyberu
    assert sorted(okno.vybrane_soubory()) == sorted(vsechny[:2] + [vsechny[5]])
    assert okno.seznam.size() == 10, "soubory ze slozky se nesmi duplikovat"


def test_prevest_dropnute_bez_platneho_vstupu(okno, tmp_path, monkeypatch):
    """Po spusteni .exe vedle sebe Archiv nebyva -- dropnute soubory musi stacit."""
    import prevod_ui

    chyby = []
    monkeypatch.setattr(prevod_ui.messagebox, "showerror",
                        lambda *a, **k: chyby.append(a))
    okno.vstup.set(os.path.join(str(tmp_path), "takova-slozka-neni"))
    assert okno.seznam.size() == 0, "neexistujici slozka nema co nabidnout"

    okno.vystup.set(str(tmp_path))
    okno.pridej_dropnute("{" + p.najdi_kusovniky(ARCHIV)[1] + "}")
    okno.prevest()
    assert not chyby, chyby
    assert [f.name for f in tmp_path.glob("Kusovník*.rtf")] == ["Kusovník_poz1_LivIng_MD.rtf"]


def test_prevest_zpracuje_jen_vybrane(okno, tmp_path):
    """Tlacitko Prevest bere jen zaskrtnute kusovniky, ne celou slozku."""
    okno.vstup.set(ARCHIV)
    okno.vystup.set(str(tmp_path))
    okno.seznam.selection_clear(0, "end")
    okno.seznam.selection_set(1)
    okno.prevest()
    assert [f.name for f in tmp_path.glob("Kusovník*.rtf")] == ["Kusovník_poz1_LivIng_MD.rtf"]


def test_domovska_slozka(monkeypatch):
    """V zabalenem .exe musi vychozi cesty mirit vedle .exe, ne do temp adresare."""
    import prevod_ui

    slozka = os.path.abspath(os.path.join(os.sep, "appky", "prevod"))
    monkeypatch.setattr(prevod_ui.sys, "frozen", True, raising=False)
    monkeypatch.setattr(prevod_ui.sys, "executable", os.path.join(slozka, "prevod.exe"))
    assert prevod_ui.domovska_slozka() == slozka

    monkeypatch.delattr(prevod_ui.sys, "frozen")
    assert prevod_ui.domovska_slozka() == os.path.dirname(os.path.abspath(prevod_ui.__file__))


if __name__ == "__main__":
    for jmeno, fn in sorted(globals().items()):
        if jmeno.startswith("test_"):
            fn()
            print("OK  ", jmeno)



