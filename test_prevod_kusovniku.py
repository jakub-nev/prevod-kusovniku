"""Kontroly prepoctu skel Corona CT 70 AS -> Schuco LivIng MD.

Spustit:  python test_prevod_kusovniku.py
"""
import glob
import os
from types import SimpleNamespace

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
    """Pozice 8 = vchodové dveře s prahem. Corona 147/107, LivIng 142/110."""
    el = p.nacti_element(glob.glob(ARCHIV + r"\*_8_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el)
    assert el.prah and [s.v_dverich for s in el.skla] == [True]
    assert [(s.sirka_nova, s.vyska_nova) for s in el.skla] == [(691.0, 1763.0)]
    assert not el.poznamky, el.poznamky


def test_okenni_kridlo_na_prahu():
    """Pozice 6 = okenní rám + vchodový práh. Dole Corona 70 (5+65), LivIng 68 (5+63)."""
    el = p.nacti_element(glob.glob(ARCHIV + r"\*_6_22_6_12_55_55.rtf")[0])[0]
    p.prepocti(el)
    assert "dole" not in el.ram_strany and p._na_prahu(el, "kridlo")
    assert [(s.sirka_nova, s.vyska_nova) for s in el.skla] == [(715.0, 1797.0)]
    assert not el.poznamky, el.poznamky


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



