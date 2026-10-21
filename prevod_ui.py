"""Okno pro převod kusovníků Corona CT 70 AS -> Schüco LivIng MD.

Spustit dvojklikem na prevod.bat, nebo:  python prevod_ui.py
Veškerý výpočet dělá prevod_kusovniku.py, tohle je jen obal: nativní okno
s webovým jádrem, vzhled je ve web/index.html.
"""
import json
import os
import subprocess
import sys

import webview
from webview.dom import DOMEventHandler

import prevod_kusovniku as prevod

MAC = sys.platform == "darwin"


def domovska_slozka():
    """Kde hledat Archiv a kam psát výsledky.

    V zabaleném .exe je __file__ v dočasném adresáři, ze kterého se program
    rozbalil - výchozí cesty musí mířit vedle spustitelného souboru.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def slozka_webu():
    """HTML se do .exe balí přes --add-data, rozbalí se do sys._MEIPASS."""
    koren = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(koren, "web")


ZDE = domovska_slozka()

# Vedle .exe se psát nedá (Program Files, podepsaný .app), domovský adresář jde vždy.
NASTAVENI = os.path.join(os.path.expanduser("~"), ".prevod_kusovniku")

# Odečet převodu: pohledové šířky profilů LivIng, podle kterých se skla přepočítávají.
# Verzálky ručně -- "b" u štulpu je katalogové označení, velké B by znamenalo něco jiného.
ODECET = (("RÁM", prevod.RAM_MM), ("KŘÍDLO", prevod.KRIDLO_MM),
          ("T-PROFIL", prevod.T_PROFIL_MM), ("ŠTULP b", prevod.STULP_MM))


def _nacti_tmavy():
    """Zapamatovaný režim. Chybějící i poškozené nastavení znamená světlý."""
    try:
        with open(NASTAVENI, encoding="utf-8") as f:
            return f.read().strip() == "tmavy"
    except OSError:
        return False


def _uloz_tmavy(tmavy):
    """Když se zapsat nedá, přepínač funguje dál -- jen si to nezapamatuje."""
    try:
        with open(NASTAVENI, "w", encoding="utf-8") as f:
            f.write("tmavy" if tmavy else "svetly")
    except OSError:
        pass


def popis(cesta):
    """Pozice a rozměry prvku -- názvy souborů z Macu bývají rozsypané."""
    zaklad = {"cesta": cesta, "pozice": os.path.basename(cesta), "kus": "", "rozmer": ""}
    try:
        el = prevod.nacti_element(cesta)[0]
    except Exception:
        return zaklad
    return {"cesta": cesta, "pozice": el.pozice, "kus": el.kus,
            "rozmer": f"{el.sirka:.0f} × {el.vyska:.0f} mm"}


class Api:
    """Co smí zavolat stránka. Veškerý výpočet zůstává v prevod_kusovniku."""

    def __init__(self):
        self.soubory = []                          # absolutní cesty v pořadí seznamu

    # --- start -----------------------------------------------------------
    def zaklad(self):
        vychozi = os.path.join(ZDE, "Archiv")
        return {"vstup": vychozi if os.path.isdir(vychozi) else ZDE,
                "vystup": os.path.join(ZDE, "LivIng_MD"),
                "odecet": [list(p) for p in ODECET],
                "tmavy": _nacti_tmavy()}

    def seznam(self, slozka):
        self.soubory = prevod.najdi_kusovniky(slozka) if os.path.isdir(slozka) else []
        return [popis(c) for c in self.soubory]

    # --- přetažení -------------------------------------------------------
    def dropnuto(self, cesty):
        """Přidá přetažené kusovníky a označí je. Složku vezme jako vstup."""
        cesty = [os.path.normpath(c) for c in cesty if c]
        slozky = [c for c in cesty if os.path.isdir(c)]
        if slozky:
            return {"vstup": slozky[0], "seznam": self.seznam(slozky[0]),
                    "nove": list(self.soubory)}

        nove = [c for c in cesty if c.lower().endswith(".rtf")]
        if not nove:
            return {"seznam": [popis(c) for c in self.soubory], "nove": [],
                    "hlaska": "Přetáhněte kusovníky (*.rtf) nebo složku s nimi."}

        for c in nove:
            if c not in self.soubory:
                self.soubory.append(c)
        self.soubory.sort()
        return {"seznam": [popis(c) for c in self.soubory], "nove": nove}

    # --- převod ----------------------------------------------------------
    def prevest(self, vstup, vystup, vybrane, corona=()):
        if not vybrane:                            # rozhoduje výběr, ne vstupní složka
            if not os.path.isdir(vstup):
                return {"stav": f"Složka s kusovníky neexistuje: {vstup}", "klic": "varovna",
                        "zalozka": "p-vyber"}
            return {"stav": "Nic není vybráno — zaškrtněte kusovníky v záložce Kusovníky.",
                    "klic": "varovna", "zalozka": "p-vyber"}
        try:
            elementy, text = prevod.spust(vstup, vystup, list(vybrane), corona)
        except Exception as chyba:
            return {"log": f"CHYBA: {chyba}", "stav": "Převod selhal.", "klic": "varovna",
                    "zalozka": "p-prubeh"}

        if not elementy:
            return {"log": text + "\nZ vybraných souborů se nepodařilo načíst žádný prvek.",
                    "radky": [], "ks": 0, "m2": "0,000",
                    "stav": "Nic k převodu.", "klic": "varovna", "zalozka": "p-prubeh"}

        radky, ks, m2 = prevod.souhrn_skel(elementy)
        potize = sum(1 for el in elementy if not el.corona for s in el.skla if not s.prepocteno)
        varovani = potize or any(el.poznamky for el in elementy)
        v_corone = sum(el.corona for el in elementy)
        stav = (f"Hotovo — {len(elementy)} pozic"
                f"{f' ({v_corone} v Coroně)' if v_corone else ''}, {ks} tabulí, "
                f"{m2:.3f} m²".replace(".", ",") + (
                    f".  POZOR: {potize} tabulí nepřepočteno (viz červené řádky)." if potize
                    else ".  Zkontrolujte červené poznámky v průběhu." if varovani
                    else ".  Všechna skla přepočtena."))
        porovnani = []
        for el in elementy:
            if el.pozice == "?":                   # nepřečtený kusovník nemá co ukázat
                continue
            r = prevod.porovnani(el)
            porovnani.append({"pozice": el.pozice, "kus": el.kus,
                              "rozmer": f"{el.sirka:.0f} × {el.vyska:.0f} mm",
                              "system": "Corona" if el.corona else "LivIng MD",
                              "original": el.soubor, "vystup": el.cil,
                              "poznamky": el.poznamky, "radky": r,
                              "zmen": sum(x["zmena"] for x in r)})
        return {"log": text, "radky": radky, "ks": ks, "porovnani": porovnani,
                "m2": f"{m2:.3f}".replace(".", ","),
                "stav": stav, "klic": "varovna" if potize else "" if varovani else "ok",
                "zalozka": "p-prubeh" if varovani else "p-souhrn"}

    def nahled(self, cesta):
        """Kusovník jako HTML pro prohlížeč originálu a výstupu vedle sebe."""
        if not (cesta.lower().endswith(".rtf") and os.path.isfile(cesta)):
            return '<p class="prazdno">Soubor neexistuje.</p>'
        return prevod.nahled(cesta)

    # --- okolí -----------------------------------------------------------
    def prochazet(self, soucasna):
        okna = webview.windows
        if not okna:
            return None
        vybrano = okna[0].create_file_dialog(webview.FOLDER_DIALOG,
                                             directory=soucasna or ZDE)
        return os.path.normpath(vybrano[0]) if vybrano else None

    def otevri(self, cesta):
        if not os.path.isdir(cesta):
            return {"ok": False, "hlaska": "Složka s výsledky zatím neexistuje."}
        if MAC:                                    # os.startfile je jen na Windows
            subprocess.run(["open", cesta], check=False)
        else:
            os.startfile(cesta)
        return {"ok": True}

    def uloz_rezim(self, tmavy):
        _uloz_tmavy(bool(tmavy))


def _pripoj_drop(okno, api):
    """Cesty přetažených souborů dá jen Python -- prohlížeč zná pouze jména."""
    def upusteno(e):
        cesty = [f.get("pywebviewFullPath") for f in e["dataTransfer"]["files"]]
        odpoved = api.dropnuto([c for c in cesty if c])
        okno.evaluate_js(f"window.prijmiDropnute({json.dumps(odpoved)})")

    okno.dom.document.events.drop += DOMEventHandler(upusteno, True, True)


def main():
    api = Api()
    okno = webview.create_window(
        "Převod kusovníků  ·  Corona CT 70 AS → Schüco LivIng MD",
        os.path.join(slozka_webu(), "index.html"),
        js_api=api, width=1080, height=830, min_size=(900, 620),
        background_color="#ffffff")
    # Výchozí private_mode: vlastní port a profil. S private_mode=False sdílí všechny
    # pywebview aplikace port 42001 i %APPDATA%\pywebview a otevírala se cizí stránka.
    # Ze zdrojaku ikona okna; v .exe soubor chybi a pywebview vezme ikonu binarky.
    ikona = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ikona.ico")
    webview.start(lambda: _pripoj_drop(okno, api), icon=ikona)


if __name__ == "__main__":
    if "--kontrola" in sys.argv:
        # CI: zabalena binarka musi mit uvnitr web/, jinak by se otevrelo prazdno
        cesta = os.path.join(slozka_webu(), "index.html")
        sys.exit(0 if os.path.isfile(cesta) else 1)
    main()
