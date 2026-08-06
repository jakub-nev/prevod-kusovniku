"""Okno pro převod kusovníků Corona CT 70 AS -> Schüco LivIng MD.

Spustit dvojklikem na prevod.bat, nebo:  python prevod_ui.py
Veškerý výpočet dělá prevod_kusovniku.py, tohle je jen obal.
"""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import prevod_kusovniku as prevod


def domovska_slozka():
    """Kde hledat Archiv a kam psát výsledky.

    V zabaleném .exe je __file__ v dočasném adresáři, ze kterého se program
    rozbalil - výchozí cesty musí mířit vedle spustitelného souboru.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ZDE = domovska_slozka()

TMAVA = "#12263a"        # nadpisy a text tabulky
SEDA = "#5b6b7c"         # vysvětlivky
CARA = "#dbe2ea"
MODRA = "#00539b"        # primární tlačítko
MODRA_TMAVA = "#003a70"
CERVENA = "#c00000"
ZELENA = "#1b7f3b"
BILA = "#ffffff"
PRUH = "#f4f7fa"         # zebra v tabulce
PODKLAD_LOGU = "#fbfcfd"

PISMO = ("Segoe UI", 9)
PISMO_TUCNE = ("Segoe UI", 9, "bold")
PISMO_NADPIS = ("Segoe UI Semibold", 14)
STROJOPIS = ("Consolas", 9)
STROJOPIS_TUCNY = ("Consolas", 9, "bold")

# Souhrn skel: (nadpis, šířka px, zarovnání) podle prevod.SOUHRN_SLOUPCE.
# Typ skla se roztahuje - je to nejdelší údaj a zároveň to, podle čeho se objednává.
SLOUPCE = [("Typ skla", 340, "w"), ("Tl.", 45, "e"), ("Šířka", 70, "e"), ("Výška", 70, "e"),
           ("Ks", 40, "e"), ("Plocha m²", 75, "e"), ("Pozice", 90, "w"), ("Poznámka", 150, "w")]
ROZTAHOVAT = "Typ skla"


def _ostre_pismo():
    """Bez tohohle je na HiDPI displeji celé okno rozmazané."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class Tlacitko(tk.Button):
    """Primární tlačítko — ttk ve vista tématu neumí vlastní barvu."""

    def __init__(self, master, **kw):
        super().__init__(master, relief="flat", borderwidth=0, cursor="hand2",
                         background=MODRA, foreground=BILA, activebackground=MODRA_TMAVA,
                         activeforeground=BILA, font=PISMO_TUCNE, padx=20, pady=6, **kw)
        self.bind("<Enter>", lambda _: self.configure(background=MODRA_TMAVA))
        self.bind("<Leave>", lambda _: self.configure(background=MODRA))


class Okno(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Převod kusovníků  ·  Corona CT 70 AS → Schüco LivIng MD")
        self.geometry("1020x700")
        self.minsize(860, 560)
        self.configure(background=BILA)
        self._styly()

        vychozi_vstup = os.path.join(ZDE, "Archiv")
        self.vstup = tk.StringVar(value=vychozi_vstup if os.path.isdir(vychozi_vstup) else ZDE)
        self.vystup = tk.StringVar(value=os.path.join(ZDE, "LivIng_MD"))
        self.stav = tk.StringVar(value="Vyber složku s kusovníky a stiskni Převést.")

        ram = ttk.Frame(self, padding=(20, 16, 20, 12))
        ram.pack(fill="both", expand=True)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(3, weight=1)

        self._hlavicka(ram).grid(row=0, column=0, sticky="ew")
        self._cesty(ram).grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self._ovladani(ram).grid(row=2, column=0, sticky="ew", pady=(14, 12))
        self._zalozky(ram).grid(row=3, column=0, sticky="nsew")
        self._stavovy_radek(ram).grid(row=4, column=0, sticky="ew", pady=(12, 0))

        self.bind("<Return>", lambda _: self.prevest())
        self.bind("<F5>", lambda _: self.prevest())
        self._na_stred()

    # --- stavba okna ------------------------------------------------------
    def _styly(self):
        s = ttk.Style(self)
        if "vista" in s.theme_names():
            s.theme_use("vista")
        s.configure(".", background=BILA, font=PISMO)
        s.configure("TFrame", background=BILA)
        s.configure("TLabel", background=BILA, foreground=TMAVA)
        s.configure("Nadpis.TLabel", font=PISMO_NADPIS)
        s.configure("Tlumene.TLabel", foreground=SEDA)
        s.configure("Popisek.TLabel", foreground=SEDA, font=("Segoe UI", 8))
        s.configure("Stav.TLabel", foreground=SEDA)
        s.configure("TNotebook", background=BILA, borderwidth=0)
        s.configure("TNotebook.Tab", font=PISMO, padding=(16, 7))
        s.configure("Souhrn.Treeview", font=STROJOPIS, rowheight=23,
                    background=BILA, fieldbackground=BILA, foreground=TMAVA, borderwidth=0)
        s.configure("Souhrn.Treeview.Heading", font=PISMO_TUCNE, padding=(4, 6))
        s.map("Souhrn.Treeview", background=[("selected", "#cfe2f5")],
              foreground=[("selected", TMAVA)])

    def _hlavicka(self, rodic):
        ram = ttk.Frame(rodic)
        ttk.Label(ram, text="Převod kusovníků", style="Nadpis.TLabel").pack(anchor="w")
        ttk.Label(ram, style="Tlumene.TLabel", wraplength=940, justify="left",
                  text=f"Corona CT 70 AS  →  Schüco LivIng MD:  rám {prevod.RAM_MM} mm, "
                       f"křídlo {prevod.KRIDLO_MM} mm, T-profil {prevod.T_PROFIL_MM} mm, "
                       f"štulp b={prevod.STULP_MM} mm.\n"
                       "Mění se rozměry skel a řezné délky okenních křídel; ostatní "
                       "profily i dveřní křídla zůstávají původní.").pack(
            anchor="w", pady=(4, 0))
        return ram

    def _cesty(self, rodic):
        ram = ttk.Frame(rodic)
        ram.columnconfigure(1, weight=1)
        for radek, (popis, promenna) in enumerate(
                (("Kusovníky (vstup)", self.vstup), ("Výstup", self.vystup))):
            ttk.Label(ram, text=popis).grid(row=radek, column=0, sticky="w", pady=4)
            ttk.Entry(ram, textvariable=promenna, font=PISMO).grid(
                row=radek, column=1, sticky="ew", padx=10)
            ttk.Button(ram, text="Procházet…", command=lambda p=promenna: self._vyber(p)).grid(
                row=radek, column=2)
        return ram

    def _ovladani(self, rodic):
        ram = ttk.Frame(rodic)
        Tlacitko(ram, text="Převést", command=self.prevest).pack(side="left")
        ttk.Button(ram, text="Otevřít složku s výsledky", command=self.otevri_vystup).pack(
            side="left", padx=10)
        ttk.Label(ram, text="Enter / F5", style="Popisek.TLabel").pack(side="left")
        return ram

    def _zalozky(self, rodic):
        self.zalozky = ttk.Notebook(rodic)
        self.zalozky.add(self._log(self.zalozky), text="Průběh převodu")
        self.zalozky.add(self._souhrn(self.zalozky), text="Souhrn skel")
        return self.zalozky

    def _log(self, rodic):
        ram = ttk.Frame(rodic, padding=1)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(0, weight=1)
        self.log = tk.Text(ram, wrap="none", font=STROJOPIS, background=PODKLAD_LOGU,
                           foreground=TMAVA, relief="flat", borderwidth=0, padx=12, pady=10,
                           highlightthickness=1, highlightbackground=CARA, highlightcolor=CARA)
        self.log.grid(row=0, column=0, sticky="nsew")
        svisle = ttk.Scrollbar(ram, orient="vertical", command=self.log.yview)
        svisle.grid(row=0, column=1, sticky="ns")
        vodorovne = ttk.Scrollbar(ram, orient="horizontal", command=self.log.xview)
        vodorovne.grid(row=1, column=0, sticky="ew")
        self.log.configure(yscrollcommand=svisle.set, xscrollcommand=vodorovne.set,
                           state="disabled")
        self.log.tag_configure("pozice", foreground=MODRA_TMAVA, font=STROJOPIS_TUCNY,
                               spacing1=6)
        self.log.tag_configure("varovani", foreground=CERVENA)
        self.log.tag_configure("souhrn", font=STROJOPIS_TUCNY, spacing1=8)
        self._vypis("Zatím nic nepřevedeno.")
        return ram

    def _souhrn(self, rodic):
        ram = ttk.Frame(rodic, padding=1)
        ram.columnconfigure(0, weight=1)
        ram.rowconfigure(0, weight=1)
        self.tabulka = ttk.Treeview(ram, style="Souhrn.Treeview", selectmode="browse",
                                    columns=[n for n, _, _ in SLOUPCE], show="headings")
        for nazev, sirka, zarovnani in SLOUPCE:
            self.tabulka.heading(nazev, text=nazev, anchor=zarovnani)
            self.tabulka.column(nazev, width=sirka, minwidth=40, anchor=zarovnani,
                                stretch=(nazev == ROZTAHOVAT))
        self.tabulka.grid(row=0, column=0, sticky="nsew")
        posuvnik = ttk.Scrollbar(ram, orient="vertical", command=self.tabulka.yview)
        posuvnik.grid(row=0, column=1, sticky="ns")
        self.tabulka.configure(yscrollcommand=posuvnik.set)
        self.tabulka.tag_configure("pruh", background=PRUH)
        self.tabulka.tag_configure("celkem", font=STROJOPIS_TUCNY, background="#e8eef5")
        self.tabulka.tag_configure("overit", foreground=CERVENA)

        self.prazdno = ttk.Label(ram, style="Tlumene.TLabel", anchor="center",
                                 text="Zatím není co objednávat — spusť Převést.")
        self.prazdno.grid(row=0, column=0, sticky="nsew", pady=40)
        return ram

    def _stavovy_radek(self, rodic):
        ram = ttk.Frame(rodic)
        ttk.Separator(ram, orient="horizontal").pack(fill="x", pady=(0, 8))
        self.stav_popisek = ttk.Label(ram, textvariable=self.stav, style="Stav.TLabel")
        self.stav_popisek.pack(anchor="w")
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
        if os.path.isdir(cesta):
            os.startfile(cesta)
        else:
            messagebox.showinfo("Není co otevřít", "Složka s výsledky zatím neexistuje.")

    def prevest(self):
        vstup, vystup = self.vstup.get(), self.vystup.get()
        if not os.path.isdir(vstup):
            messagebox.showerror("Chyba", f"Složka s kusovníky neexistuje:\n{vstup}")
            return
        self._nastav_stav("Převádím…", SEDA)
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            elementy, text = prevod.spust(vstup, vystup)
        except Exception as chyba:
            self._vypis(f"CHYBA: {chyba}")
            self._nastav_stav("Převod selhal.", CERVENA)
            messagebox.showerror("Chyba při převodu", str(chyba))
            return
        finally:
            self.configure(cursor="")

        self._vypis(text)
        if not elementy:
            self._napln_souhrn([])
            self._vypis("Ve zvolené složce nejsou žádné kusovníky (*.rtf).")
            self._nastav_stav("Nic k převodu — složka neobsahuje kusovníky.", CERVENA)
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
            CERVENA if potize else TMAVA if varovani else ZELENA)
        self.zalozky.select(0 if varovani else 1)

    def _nastav_stav(self, text, barva):
        self.stav.set(text)
        self.stav_popisek.configure(foreground=barva)

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
