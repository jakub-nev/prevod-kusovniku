"""Okno pro převod kusovníků Corona CT 70 AS -> Schüco LivIng MD.

Spustit dvojklikem na prevod.bat, nebo:  python prevod_ui.py
Veškerý výpočet dělá prevod_kusovniku.py, tohle je jen obal.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

import prevod_kusovniku as prevod

try:                                               # drag & drop: TkDnD přes tkinterdnd2
    from tkinterdnd2 import DND_FILES, TkinterDnD
    ZAKLAD_OKNA = TkinterDnD.Tk
except ImportError:                                # bez knihovny okno funguje dál, jen bez dropu
    DND_FILES, ZAKLAD_OKNA = None, tk.Tk


def domovska_slozka():
    """Kde hledat Archiv a kam psát výsledky.

    V zabaleném .exe je __file__ v dočasném adresáři, ze kterého se program
    rozbalil - výchozí cesty musí mířit vedle spustitelného souboru.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ZDE = domovska_slozka()
MAC = sys.platform == "darwin"

# Chladná neutrální škála + jeden akcent: petrolejová je barva hrany float skla.
SVETLY = dict(
    text="#10151a",          # nadpisy, čísla, text tabulky
    tlumeny="#5a6672",       # vysvětlivky
    popisek="#97a1ab",       # popisky, jednotky
    linka="#e3e7ea",         # linky a rámečky polí
    podklad="#f4f6f7",       # podklad okna, pod panely
    panel="#ffffff",         # plocha záložek a vstupních polí
    akcent="#0f5a63",        # primární tlačítko, fokus, šipka převodu
    akcent_tmavy="#0a444b",
    akcent_svetly="#14707b",
    na_akcentu="#ffffff",    # text v primárním tlačítku
    vyber="#e6f0f1",         # označený řádek v seznamu i tabulce
    drop="#f1f7f8",          # seznam při přetažení; jinak než vyber, ať je výběr znát
    pruh="#fafbfc",          # sotva znatelná zebra v tabulce
    celkem="#eef1f2",
    varovna="#a8342a",
    ok="#1c6b4a")

# Tmavý režim: podklad není černý a akcent se musí rozsvítit, jinak na tmavém zanikne.
TMAVY = dict(
    text="#e6eaed",
    tlumeny="#a3adb5",
    popisek="#8a959d",
    linka="#2b3236",
    podklad="#14181b",
    panel="#1c2124",
    akcent="#4fb3bf",
    akcent_tmavy="#3d9aa5",
    akcent_svetly="#63c5d1",
    na_akcentu="#10151a",    # rozsvícený akcent unese jen tmavý text
    vyber="#23383c",
    drop="#182629",          # tmavší než vyber, ať je výběr znát i při přetažení
    pruh="#20262a",
    celkem="#262d31",
    varovna="#f08a7e",
    ok="#5fc08d")

B = dict(SVETLY)             # aktivní paleta, _prepni_rezim ji přepíše na místě

# macOS renderuje body ~1:1 do pixelů, Windows při 96 dpi zhruba 1,33x -- proto dvě sady.
VELIKOSTI = (dict(telo=13, popisek=11, nadpis=27, cisla=12, odecet=19, radek=30) if MAC
             else dict(telo=10, popisek=9, nadpis=21, cisla=10, odecet=15, radek=27))

# Souhrn skel: (nadpis, šířka px, zarovnání) podle prevod.SOUHRN_SLOUPCE.
# Typ skla se roztahuje - je to nejdelší údaj a zároveň to, podle čeho se objednává.
SLOUPCE = [("Typ skla", 340, "w"), ("Tl.", 45, "e"), ("Šířka", 70, "e"), ("Výška", 70, "e"),
           ("Ks", 40, "e"), ("Plocha m²", 75, "e"), ("Pozice", 90, "w"), ("Poznámka", 150, "w")]
ROZTAHOVAT = "Typ skla"

# Odečet převodu: pohledové šířky profilů LivIng, podle kterých se skla přepočítávají.
# Verzálky ručně -- "b" u štulpu je katalogové označení, velké B by znamenalo něco jiného.
ODECET = (("RÁM", prevod.RAM_MM), ("KŘÍDLO", prevod.KRIDLO_MM),
          ("T-PROFIL", prevod.T_PROFIL_MM), ("ŠTULP b", prevod.STULP_MM))


# Vedle .exe se psát nedá (Program Files, podepsaný .app), domovský adresář jde vždy.
NASTAVENI = os.path.join(os.path.expanduser("~"), ".prevod_kusovniku")


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


def _ostre_pismo():
    """Bez tohohle je na HiDPI displeji celé okno rozmazané."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _rodina(*jmena):
    """První nainstalovaný font ze seznamu. Windows a macOS nesdílí skoro nic."""
    dostupne = set(tkfont.families())
    return next((j for j in jmena if j in dostupne),
                tkfont.nametofont("TkDefaultFont").cget("family"))


PISMA = {}


def _pisma():
    """Rodiny jdou přečíst až po vzniku rootu. Ntice, ne pojmenované fonty:

    tkfont.Font(name=...) smaže font v __del__, takže bez držené reference
    zmizí dřív, než se stihne vykreslit -- a widgety tiše spadnou na Arial.
    """
    ui = _rodina("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans")
    displej = _rodina("Segoe UI Semibold", "SF Pro Display", "Helvetica Neue", ui)
    cisla = _rodina("Consolas", "SF Mono", "Menlo", "DejaVu Sans Mono")
    v = VELIKOSTI
    PISMA.update(
        telo=(ui, v["telo"]),
        telo_tucne=(ui, v["telo"], "bold"),
        popisek=(ui, v["popisek"]),
        nadpis=(displej, v["nadpis"], "normal" if "Semibold" in displej else "bold"),
        cisla=(cisla, v["cisla"]),
        cisla_tucna=(cisla, v["cisla"], "bold"),
        odecet=(cisla, v["odecet"]))


def _prostrkat(text):
    """Proložení vlasovou mezerou; jen pro popisky odečtu, verzálky jinak drží při sobě."""
    return " ".join(text)


class Okno(ZAKLAD_OKNA):
    def __init__(self):
        super().__init__()
        self.tmavy = _nacti_tmavy()                # paletu vybrat dřív, než vznikne první widget
        self._nastav_paletu()
        self.title("Převod kusovníků  ·  Corona CT 70 AS → Schüco LivIng MD")
        self.geometry("1080x760")
        self.minsize(920, 620)
        self.configure(background=B["podklad"])
        _pisma()
        self._styly()

        vychozi_vstup = os.path.join(ZDE, "Archiv")
        self.vstup = tk.StringVar(value=vychozi_vstup if os.path.isdir(vychozi_vstup) else ZDE)
        self.vystup = tk.StringVar(value=os.path.join(ZDE, "LivIng_MD"))
        self.stav = tk.StringVar(value="Vyber kusovníky a stiskni Převést.")
        self.vybrano = tk.StringVar(value="")
        self.soubory = []
        self.dnd_aktivni = bool(DND_FILES)
        self.klic_stavu = "popisek"
        self.linky = []                            # vlasové linky se přebarvují ručně

        ram = ttk.Frame(self, padding=(28, 24, 28, 18))
        ram.pack(fill="both", expand=True)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(4, weight=1)

        self._hlavicka(ram).grid(row=0, column=0, sticky="ew")
        self._cesty(ram).grid(row=1, column=0, sticky="ew", pady=(24, 0))
        self._ovladani(ram).grid(row=2, column=0, sticky="ew", pady=(20, 0))
        self._zalozky(ram).grid(row=4, column=0, sticky="nsew", pady=(22, 0))
        self._stavovy_radek(ram).grid(row=5, column=0, sticky="ew", pady=(16, 0))

        self.bind("<Return>", lambda _: self.prevest())
        self.bind("<F5>", lambda _: self.prevest())
        self.vstup.trace_add("write", lambda *_: self.nacti_seznam())
        self._zapni_drop(self)                     # celé okno, ať nezáleží kam se pustí
        self._zapni_drop(self.seznam)
        self.nacti_seznam()
        self._na_stred()

    def _zapni_drop(self, widget):
        """Přijme přetažené soubory. Bez tkinterdnd2 nedělá nic."""
        if not self.dnd_aktivni:
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<DropEnter>>", lambda _: self._drag_enter())
        widget.dnd_bind("<<DropLeave>>", lambda _: self._drag_leave())
        widget.dnd_bind("<<Drop>>", lambda udalost: self._drop(udalost.data))

    def _drag_enter(self):
        """Soubor je nad oknem -- ať je vidět, že se přijme."""
        self.seznam.configure(background=B["drop"])
        self.obal.configure(background=B["drop"], highlightbackground=B["akcent"],
                            highlightcolor=B["akcent"], highlightthickness=2)
        self.zalozky.select(0)

    def _drag_leave(self):
        self.seznam.configure(background=B["panel"])
        self.obal.configure(background=B["panel"], highlightbackground=B["linka"],
                            highlightcolor=B["linka"], highlightthickness=0)

    def _drop(self, data):
        self._drag_leave()
        self.pridej_dropnute(data)

    # --- světlý / tmavý režim ---------------------------------------------
    def _popis_rezimu(self):
        """Tlačítko pojmenované tím, co udělá, ne tím, kde zrovna jsme."""
        return "Světlý režim" if self.tmavy else "Tmavý režim"

    def _nastav_paletu(self):
        B.clear()
        B.update(TMAVY if self.tmavy else SVETLY)

    def _prepni_rezim(self):
        self.tmavy = not self.tmavy
        self._nastav_paletu()
        _uloz_tmavy(self.tmavy)
        self._prebarvi()

    def _prebarvi(self):
        """ttk widgety berou barvu ze stylu, klasické tk widgety si ji drží samy."""
        self._styly()
        self.configure(background=B["podklad"])
        self.prepinac.configure(text=self._popis_rezimu())
        self.seznam.configure(background=B["panel"], foreground=B["text"],
                              selectbackground=B["vyber"], selectforeground=B["text"])
        self._drag_leave()                         # obal seznamu do klidové barvy
        self.log.configure(background=B["panel"], foreground=B["text"])
        self.log.tag_configure("pozice", foreground=B["akcent"])
        self.log.tag_configure("varovani", foreground=B["varovna"])
        self.tabulka.tag_configure("pruh", background=B["pruh"])
        self.tabulka.tag_configure("celkem", background=B["celkem"])
        self.tabulka.tag_configure("overit", foreground=B["varovna"])
        for cara in self.linky:
            cara.configure(background=B["linka"])
        self._nastav_stav(self.stav.get(), self.klic_stavu)

    # --- stavba okna ------------------------------------------------------
    def _styly(self):
        """Všude clam: jako jediné vestavěné téma bere barvy i na macOS."""
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=B["podklad"], foreground=B["text"], font=PISMA["telo"],
                    focuscolor=B["akcent"], borderwidth=0)
        s.configure("TFrame", background=B["podklad"])
        s.configure("Panel.TFrame", background=B["panel"])
        s.configure("TLabel", background=B["podklad"], foreground=B["text"])
        s.configure("Nadpis.TLabel", font=PISMA["nadpis"])
        s.configure("Tlumene.TLabel", foreground=B["tlumeny"])
        s.configure("Popisek.TLabel", foreground=B["popisek"], font=PISMA["popisek"])
        s.configure("Sipka.TLabel", foreground=B["akcent"])
        s.configure("Odecet.TLabel", font=PISMA["odecet"])
        s.configure("Jednotka.TLabel", foreground=B["popisek"], font=PISMA["popisek"])
        # popisky uvnitř záložek sedí na ploše panelu, ne na podkladu okna
        for jmeno, kw in (("PanelTlumene.TLabel", {"foreground": B["tlumeny"]}),
                          ("PanelPopisek.TLabel", {"foreground": B["popisek"],
                                                   "font": PISMA["popisek"]})):
            s.configure(jmeno, background=B["panel"], **kw)

        s.configure("TEntry", fieldbackground=B["panel"], foreground=B["text"], insertcolor=B["akcent"],
                    bordercolor=B["linka"], lightcolor=B["linka"], darkcolor=B["linka"],
                    borderwidth=1, padding=(10, 8))
        s.map("TEntry", bordercolor=[("focus", B["akcent"])], lightcolor=[("focus", B["akcent"])],
              darkcolor=[("focus", B["akcent"])])

        # výchozí tlačítko je tiché (obrys), primární má vlastní styl
        s.configure("TButton", background=B["panel"], foreground=B["text"], font=PISMA["telo"],
                    bordercolor=B["linka"], lightcolor=B["panel"], darkcolor=B["panel"],
                    borderwidth=1, padding=(14, 8), relief="flat", anchor="center")
        s.map("TButton", background=[("pressed", B["podklad"]), ("active", B["podklad"])],
              bordercolor=[("pressed", B["popisek"]), ("active", B["popisek"])],
              lightcolor=[("pressed", B["podklad"]), ("active", B["podklad"])],
              darkcolor=[("pressed", B["podklad"]), ("active", B["podklad"])],
              foreground=[("disabled", B["popisek"])])
        s.configure("Hlavni.TButton", background=B["akcent"], foreground=B["na_akcentu"],
                    font=PISMA["telo_tucne"],
                    bordercolor=B["akcent"], lightcolor=B["akcent"], darkcolor=B["akcent"],
                    borderwidth=1, padding=(28, 10))
        s.map("Hlavni.TButton",
              background=[("pressed", B["akcent_tmavy"]), ("active", B["akcent_svetly"])],
              bordercolor=[("pressed", B["akcent_tmavy"]), ("active", B["akcent_svetly"])],
              lightcolor=[("pressed", B["akcent_tmavy"]), ("active", B["akcent_svetly"])],
              darkcolor=[("pressed", B["akcent_tmavy"]), ("active", B["akcent_svetly"])],
              foreground=[("disabled", B["popisek"])])

        # rámeček panelu je v barvě podkladu: vybraná záložka a plocha pod ní
        # tak splynou v jednu bílou plochu a nevzniká rámeček v rámečku
        s.configure("TNotebook", background=B["podklad"], borderwidth=0, tabmargins=(0, 0, 0, 0),
                    bordercolor=B["podklad"], lightcolor=B["podklad"], darkcolor=B["podklad"])
        s.configure("TNotebook.Tab", background=B["podklad"], foreground=B["popisek"], font=PISMA["telo"],
                    bordercolor=B["podklad"], lightcolor=B["podklad"], darkcolor=B["podklad"],
                    borderwidth=0, padding=(20, 10))
        s.map("TNotebook.Tab", background=[("selected", B["panel"])], foreground=[("selected", B["text"])],
              lightcolor=[("selected", B["panel"])], darkcolor=[("selected", B["panel"])],
              bordercolor=[("selected", B["panel"])])

        s.configure("Souhrn.Treeview", font=PISMA["cisla"], rowheight=VELIKOSTI["radek"],
                    background=B["panel"], fieldbackground=B["panel"], foreground=B["text"], borderwidth=0,
                    bordercolor=B["panel"], lightcolor=B["panel"], darkcolor=B["panel"])
        s.configure("Souhrn.Treeview.Heading", font=PISMA["popisek"], foreground=B["popisek"],
                    background=B["panel"], relief="flat", borderwidth=0, padding=(6, 10))
        s.map("Souhrn.Treeview.Heading", background=[("active", B["panel"])])
        s.map("Souhrn.Treeview", background=[("selected", B["vyber"])], foreground=[("selected", B["text"])])

        for smer in ("Vertical", "Horizontal"):    # posuvníky bez šipek, jen tenký palec
            s.layout(f"Tenky.{smer}.TScrollbar", [
                (f"{smer}.Scrollbar.trough", {
                    "sticky": "ns" if smer == "Vertical" else "ew",
                    "children": [(f"{smer}.Scrollbar.thumb",
                                  {"expand": 1, "sticky": "nswe"})]})])
            s.configure(f"Tenky.{smer}.TScrollbar", troughcolor=B["panel"], background=B["linka"],
                        bordercolor=B["panel"], lightcolor=B["linka"], darkcolor=B["linka"],
                        borderwidth=3, arrowsize=0, width=12)
            s.map(f"Tenky.{smer}.TScrollbar", background=[("active", B["popisek"])])

    def _linka(self, rodic, svisla=False):
        """Vlasová linka. Drží se v self.linky, aby se dala přebarvit při přepnutí režimu."""
        rozmer = {"width": 1} if svisla else {"height": 1}
        cara = tk.Frame(rodic, background=B["linka"], borderwidth=0, highlightthickness=0,
                        **rozmer)
        self.linky.append(cara)
        return cara

    def _posuvnik(self, rodic, smer, prikaz):
        return ttk.Scrollbar(rodic, orient=smer.lower(), command=prikaz,
                             style=f"Tenky.{smer}.TScrollbar")

    def _hlavicka(self, rodic):
        ram = ttk.Frame(rodic)
        radek_nadpisu = ttk.Frame(ram)
        radek_nadpisu.pack(fill="x")
        ttk.Label(radek_nadpisu, text="Převod kusovníků", style="Nadpis.TLabel").pack(side="left")
        self.prepinac = ttk.Button(radek_nadpisu, text=self._popis_rezimu(),
                                   command=self._prepni_rezim)
        self.prepinac.pack(side="right", anchor="n")

        prevod_radek = ttk.Frame(ram)
        prevod_radek.pack(anchor="w", pady=(6, 0))
        ttk.Label(prevod_radek, text="Corona CT 70 AS", style="Tlumene.TLabel").pack(side="left")
        ttk.Label(prevod_radek, text="→", style="Sipka.TLabel").pack(side="left", padx=10)
        ttk.Label(prevod_radek, text="Schüco LivIng MD", style="Tlumene.TLabel").pack(side="left")

        self._odecet(ram).pack(anchor="w", pady=(20, 0))
        ttk.Label(ram, style="Tlumene.TLabel", wraplength=900, justify="left",
                  text="Mění se rozměry skel a řezné délky okenních křídel. Ostatní "
                       "profily i dveřní křídla zůstávají původní.").pack(anchor="w",
                                                                         pady=(18, 0))
        self._linka(ram).pack(fill="x", pady=(18, 0))
        return ram

    def _odecet(self, rodic):
        """Pohledové šířky profilů LivIng jako odečet přístroje -- to je celý převod."""
        ram = ttk.Frame(rodic)
        for i, (popis, mm) in enumerate(ODECET):
            if i:
                self._linka(ram, svisla=True).grid(row=0, column=2 * i - 1, rowspan=2,
                                                   sticky="ns", padx=22, pady=2)
            ttk.Label(ram, text=_prostrkat(popis), style="Popisek.TLabel").grid(
                row=0, column=2 * i, sticky="w")
            hodnota = ttk.Frame(ram)
            hodnota.grid(row=1, column=2 * i, sticky="w", pady=(4, 0))
            ttk.Label(hodnota, text=f"{mm}", style="Odecet.TLabel").pack(side="left")
            ttk.Label(hodnota, text="mm", style="Jednotka.TLabel").pack(side="left",
                                                                       padx=(4, 0), pady=(4, 0))
        return ram

    def _cesty(self, rodic):
        ram = ttk.Frame(rodic)
        ram.columnconfigure(1, weight=1)
        for radek, (popis, promenna) in enumerate(
                (("Kusovníky", self.vstup), ("Výstup", self.vystup))):
            ttk.Label(ram, text=popis, style="Tlumene.TLabel").grid(
                row=radek, column=0, sticky="w", pady=6)
            ttk.Entry(ram, textvariable=promenna, font=PISMA["cisla"]).grid(
                row=radek, column=1, sticky="ew", padx=(18, 10), pady=6)
            ttk.Button(ram, text="Procházet…", command=lambda p=promenna: self._vyber(p)).grid(
                row=radek, column=2, pady=6)
        return ram

    def _ovladani(self, rodic):
        ram = ttk.Frame(rodic)
        ttk.Button(ram, text="Převést", style="Hlavni.TButton",
                   command=self.prevest).pack(side="left")
        ttk.Button(ram, text="Otevřít složku s výsledky", command=self.otevri_vystup).pack(
            side="left", padx=12)
        ttk.Label(ram, text="Enter / F5", style="Popisek.TLabel").pack(side="left", padx=4)
        return ram

    def _zalozky(self, rodic):
        self.zalozky = ttk.Notebook(rodic)
        self.zalozky.add(self._zalozka_vyberu(self.zalozky), text="Kusovníky")
        self.zalozky.add(self._log(self.zalozky), text="Průběh převodu")
        self.zalozky.add(self._souhrn(self.zalozky), text="Souhrn skel")
        return self.zalozky

    def _zalozka_vyberu(self, rodic):
        ram = ttk.Frame(rodic, style="Panel.TFrame", padding=16)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(1, weight=1)

        lista = ttk.Frame(ram, style="Panel.TFrame")
        lista.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ttk.Button(lista, text="Vybrat vše",
                   command=lambda: self._oznac(True)).pack(side="left")
        ttk.Button(lista, text="Zrušit výběr",
                   command=lambda: self._oznac(False)).pack(side="left", padx=8)
        ttk.Label(lista, textvariable=self.vybrano, style="PanelTlumene.TLabel").pack(
            side="left", padx=10)
        ttk.Label(lista, style="PanelPopisek.TLabel",
                  text=("kusovníky sem jdou přetáhnout myší" if DND_FILES
                        else "přetahování nedostupné (chybí tkinterdnd2)")).pack(side="right")

        # Listbox neumí vnitřní odsazení, obal mu dělá vzduch kolem textu.
        # Bez rámečku; ten se objeví až jako petrolejový prstenec při přetažení.
        self.obal = tk.Frame(ram, background=B["panel"], highlightthickness=0,
                             highlightbackground=B["linka"], highlightcolor=B["linka"])
        self.obal.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.obal.columnconfigure(0, weight=1)
        self.obal.rowconfigure(0, weight=1)

        self.seznam = tk.Listbox(self.obal, selectmode="multiple", activestyle="none",
                                 font=PISMA["cisla"], background=B["panel"], foreground=B["text"],
                                 selectbackground=B["vyber"], selectforeground=B["text"],
                                 relief="flat", borderwidth=0, highlightthickness=0)
        self.seznam.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=10)
        posuvnik = self._posuvnik(self.obal, "Vertical", self.seznam.yview)
        posuvnik.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=10)
        self.seznam.configure(yscrollcommand=posuvnik.set)
        self.seznam.bind("<<ListboxSelect>>", lambda _: self._spocitej_vybrane())
        return ram

    def nacti_seznam(self):
        """Naplní seznam kusovníky ze vstupní složky, všechny předvybrané."""
        slozka = self.vstup.get()
        self.soubory = prevod.najdi_kusovniky(slozka) if os.path.isdir(slozka) else []
        self.seznam.delete(0, "end")
        for cesta in self.soubory:
            self.seznam.insert("end", self._popis(cesta))
        self._oznac(True)

    @staticmethod
    def _popis(cesta):
        """Pozice a rozměry prvku -- názvy souborů z Macu bývají rozsypané."""
        try:
            el = prevod.nacti_element(cesta)[0]
            return f"pozice {el.pozice:<5} {el.kus:>2} ks   {el.sirka:.0f} × {el.vyska:.0f} mm"
        except Exception:
            return os.path.basename(cesta)

    def vybrane_soubory(self):
        return [self.soubory[i] for i in self.seznam.curselection()]

    def pridej_dropnute(self, data):
        """Přidá do seznamu přetažené kusovníky a označí je. Složku vezme jako vstup."""
        cesty = [os.path.normpath(c) for c in self.tk.splitlist(data)]
        slozky = [c for c in cesty if os.path.isdir(c)]
        if slozky:
            self.vstup.set(slozky[0])              # trace na vstup přenačte seznam sám
            return

        nove = [c for c in cesty if c.lower().endswith(".rtf")]
        if not nove:
            self._nastav_stav("Přetáhni kusovníky (*.rtf) nebo složku s nimi.", "varovna")
            return

        drzene = set(self.vybrane_soubory()) | set(nove)
        for cesta in nove:
            if cesta not in self.soubory:
                self.soubory.append(cesta)
        self.soubory.sort()
        self.seznam.delete(0, "end")
        for cesta in self.soubory:
            self.seznam.insert("end", self._popis(cesta))
        for i, cesta in enumerate(self.soubory):
            if cesta in drzene:
                self.seznam.selection_set(i)
        self._spocitej_vybrane()

    def _oznac(self, vse):
        if self.soubory:
            (self.seznam.selection_set if vse else self.seznam.selection_clear)(0, "end")
        self._spocitej_vybrane()

    def _spocitej_vybrane(self):
        pocet, celkem = len(self.seznam.curselection()), len(self.soubory)
        self.vybrano.set(f"vybráno {pocet} z {celkem}" if celkem
                         else "žádné kusovníky (*.rtf) — přetáhni je sem")

    def _log(self, rodic):
        ram = ttk.Frame(rodic, style="Panel.TFrame", padding=16)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(0, weight=1)
        self.log = tk.Text(ram, wrap="none", font=PISMA["cisla"], background=B["panel"],
                           foreground=B["text"], relief="flat", borderwidth=0, padx=4, pady=2,
                           highlightthickness=0, spacing1=1, spacing3=1)
        self.log.grid(row=0, column=0, sticky="nsew")
        svisle = self._posuvnik(ram, "Vertical", self.log.yview)
        svisle.grid(row=0, column=1, sticky="ns")
        vodorovne = self._posuvnik(ram, "Horizontal", self.log.xview)
        vodorovne.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.log.configure(yscrollcommand=svisle.set, xscrollcommand=vodorovne.set,
                           state="disabled")
        self.log.tag_configure("pozice", foreground=B["akcent"], font=PISMA["cisla_tucna"], spacing1=10)
        self.log.tag_configure("varovani", foreground=B["varovna"])
        self.log.tag_configure("souhrn", font=PISMA["cisla_tucna"], spacing1=12)
        self._vypis("Zatím nic nepřevedeno.")
        return ram

    def _souhrn(self, rodic):
        ram = ttk.Frame(rodic, style="Panel.TFrame", padding=16)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(0, weight=1)
        self.tabulka = ttk.Treeview(ram, style="Souhrn.Treeview", selectmode="browse",
                                    columns=[n for n, _, _ in SLOUPCE], show="headings")
        for nazev, sirka, zarovnani in SLOUPCE:
            self.tabulka.heading(nazev, text=nazev, anchor=zarovnani)
            self.tabulka.column(nazev, width=sirka, minwidth=40, anchor=zarovnani,
                                stretch=(nazev == ROZTAHOVAT))
        self.tabulka.grid(row=0, column=0, sticky="nsew")
        posuvnik = self._posuvnik(ram, "Vertical", self.tabulka.yview)
        posuvnik.grid(row=0, column=1, sticky="ns")
        self.tabulka.configure(yscrollcommand=posuvnik.set)
        self.tabulka.tag_configure("pruh", background=B["pruh"])
        self.tabulka.tag_configure("celkem", font=PISMA["cisla_tucna"], background=B["celkem"])
        self.tabulka.tag_configure("overit", foreground=B["varovna"])

        self.prazdno = ttk.Label(ram, style="PanelTlumene.TLabel", anchor="center",
                                 text="Zatím není co objednávat — spusť Převést.")
        self.prazdno.grid(row=0, column=0, sticky="nsew", pady=40)
        return ram

    def _stavovy_radek(self, rodic):
        ram = ttk.Frame(rodic)
        self._linka(ram).pack(fill="x", pady=(0, 12))
        radek = ttk.Frame(ram)
        radek.pack(fill="x")
        # podklad nechat na stylu TLabel, ať se sám přebarví s režimem
        self.tecka = ttk.Label(radek, text="●", font=PISMA["popisek"])
        self.tecka.pack(side="left", padx=(0, 8))
        self.stav_popisek = ttk.Label(radek, textvariable=self.stav)
        self.stav_popisek.pack(side="left")
        self._nastav_stav(self.stav.get(), self.klic_stavu)   # tečka do klidové šedé
        return ram

    def _na_stred(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    # --- chování ----------------------------------------------------------
    def _vyber(self, promenna):
        cesta = filedialog.askdirectory(initialdir=promenna.get() or ZDE)
        if cesta:
            promenna.set(os.path.normpath(cesta))

    def otevri_vystup(self):
        cesta = self.vystup.get()
        if not os.path.isdir(cesta):
            messagebox.showinfo("Není co otevřít", "Složka s výsledky zatím neexistuje.")
            return
        if MAC:                                    # os.startfile je jen na Windows
            subprocess.run(["open", cesta], check=False)
        else:
            os.startfile(cesta)

    def prevest(self):
        vstup, vystup = self.vstup.get(), self.vystup.get()
        vybrane = self.vybrane_soubory()
        if not vybrane:                            # rozhoduje výběr, ne vstupní složka
            self.zalozky.select(0)
            if not os.path.isdir(vstup):
                messagebox.showerror("Chyba", f"Složka s kusovníky neexistuje:\n{vstup}\n\n"
                                              "Vyber jinou, nebo sem kusovníky přetáhni.")
                return
            self._nastav_stav("Nic není vybráno — zaškrtni kusovníky v záložce Kusovníky.",
                              "varovna")
            return
        self._nastav_stav(f"Převádím {len(vybrane)} kusovníků…", "popisek")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            elementy, text = prevod.spust(vstup, vystup, vybrane)
        except Exception as chyba:
            self._vypis(f"CHYBA: {chyba}")
            self._nastav_stav("Převod selhal.", "varovna")
            messagebox.showerror("Chyba při převodu", str(chyba))
            return
        finally:
            self.configure(cursor="")

        self._vypis(text)
        if not elementy:
            self._napln_souhrn([])
            self._vypis("Z vybraných souborů se nepodařilo načíst žádný prvek.")
            self._nastav_stav("Nic k převodu.", "varovna")
            return

        radky, ks, m2 = prevod.souhrn_skel(elementy)
        self._napln_souhrn(radky, ks, m2)
        potize = sum(1 for el in elementy for s in el.skla if not s.prepocteno)
        varovani = potize or any(el.poznamky for el in elementy)
        self._nastav_stav(
            f"Hotovo — {len(elementy)} pozic, {ks} tabulí, "
            f"{m2:.3f} m²".replace(".", ",") + (
                f".  POZOR: {potize} tabulí nepřepočteno (viz červené řádky)." if potize
                else ".  Zkontroluj červené poznámky v průběhu." if varovani
                else ".  Všechna skla přepočtena."),
            "varovna" if potize else "text" if varovani else "ok")
        self.zalozky.select(1 if varovani else 2)   # 0 = výběr, 1 = průběh, 2 = souhrn

    def _nastav_stav(self, text, klic="popisek"):
        """Barvu nese tečka; text zčervená jen když je co řešit.

        Ukládá se klíč palety, ne hotová barva -- po přepnutí režimu se překreslí.
        """
        self.stav.set(text)
        self.klic_stavu = klic
        self.tecka.configure(foreground=B[klic])
        self.stav_popisek.configure(foreground=B["varovna" if klic == "varovna" else "text"])

    def _vypis(self, text):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for radek in text.splitlines():
            holy = radek.strip()
            if holy.startswith(("!", "POZOR", "CHYBA")):
                znacka = "varovani"
            elif radek.startswith("Pozice"):
                znacka = "pozice"
            elif holy.startswith("Celkem"):
                znacka = "souhrn"
            else:
                znacka = ""
            self.log.insert("end", radek + "\n", znacka)
        self.log.configure(state="disabled")

    def _napln_souhrn(self, radky, ks=0, m2=0.0):
        self.tabulka.delete(*self.tabulka.get_children())
        for i, radek in enumerate(radky):
            znacky = ["pruh"] if i % 2 else []
            if radek[-1]:                                  # neprázdná poznámka = neověřeno
                znacky.append("overit")
            self.tabulka.insert("", "end", values=radek, tags=znacky)
        if radky:
            self.tabulka.insert("", "end", tags=["celkem"], values=(
                "CELKEM", "", "", "", ks, f"{m2:.3f}".replace(".", ","), "", ""))
        self.prazdno.grid_remove() if radky else self.prazdno.grid()


if __name__ == "__main__":
    _ostre_pismo()
    Okno().mainloop()
