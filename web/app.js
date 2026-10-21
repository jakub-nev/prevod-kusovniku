"use strict";
/* Obsluha okna. Veskery vypocet zustava v Pythonu, tohle jen vola api a kresli. */

const $ = (s) => document.querySelector(s);
const stav = { soubory: [], vybrane: new Set(), corona: new Set(), porovnani: [], poz: 0 };

/* Bez pywebview (tj. v prohlizeci pri ladeni vzhledu) se pouziji ukazkova data,
   at jde stranka otevrit a doladit bez spousteni cele aplikace.
   Pozor: window.pywebview vznika az po nacteni skriptu, takze se to nesmi
   rozhodovat hned pri parsovani -- jinak bezi na ukazkach i v aplikaci. */
let UKAZKA = true;
const api = () => window.pywebview.api;

const MOCK = {
  zaklad: {
    vstup: "E:\\Documents\\GitHub\\prevod-kusovniku\\Archiv",
    vystup: "E:\\Documents\\GitHub\\prevod-kusovniku\\LivIng_MD",
    tmavy: false,
    odecet: [["RÁM", "70 / 80"], ["KŘÍDLO", "83 / 110 / 125"], ["T-PROFIL", 92], ["ŠTULP b", 74]],
  },
  seznam: [
    ["1.1", 2, "2045 × 1355 mm"], ["1", 4, "2045 × 1355 mm"], ["2.1", 3, "550 × 845 mm"],
    ["2", 3, "550 × 845 mm"], ["3", 1, "2335 × 1350 mm"], ["4", 1, "1145 × 1345 mm"],
    ["5", 1, "1145 × 590 mm"], ["6", 1, "915 × 1965 mm"], ["7", 1, "880 × 1950 mm"],
    ["8", 1, "975 × 2015 mm"],
  ].map(([pozice, kus, rozmer], i) => ({ cesta: "K" + i + ".rtf", pozice, kus, rozmer })),
};

/* ---------- vykreslovani ---------- */
function kresliOdecet(polozky) {
  $("#odecet").innerHTML = polozky
    .map(([popis, mm]) => `<div><dt>${popis}</dt><dd>${mm}<i>mm</i></dd></div>`)
    .join("");
}

const FAJFKA = '<svg viewBox="0 0 12 12" fill="none" stroke-width="2.2" stroke-linecap="round"' +
               ' stroke-linejoin="round"><path d="M2 6.4 4.8 9 10 3.2"/></svg>';

function kresliSeznam() {
  const s = $("#seznam");
  if (!stav.soubory.length) {
    s.innerHTML = '<p class="prazdno">Žádné kusovníky (*.rtf) — přetáhněte je sem.</p>';
  } else {
    s.innerHTML = stav.soubory.map((f) => `
      <div class="polozka" data-cesta="${encodeURIComponent(f.cesta)}"
           role="option" aria-selected="${stav.vybrane.has(f.cesta)}">
        <span class="box">${FAJFKA}</span>
        <span>pozice ${f.pozice}</span>
        <span class="rozmer">${f.kus} ks</span>
        <span class="rozmer">${f.rozmer}</span>
        <button class="system" aria-pressed="${stav.corona.has(f.cesta)}"
                title="Corona = pozice se nepřevádí, skla jdou do objednávky beze změny"
          >${stav.corona.has(f.cesta) ? "Corona" : "LivIng MD"}</button>
      </div>`).join("");
  }
  $("#pocet").textContent = stav.soubory.length
    ? `vybráno ${stav.vybrane.size} z ${stav.soubory.length}` : "";
}

function kresliLog(text) {
  const znacka = (r) => {
    const holy = r.trim();
    if (holy.startsWith("!") || holy.startsWith("POZOR") || holy.startsWith("CHYBA")) return "varovani";
    if (r.startsWith("Pozice")) return "pozice";
    if (holy.startsWith("Celkem")) return "souhrn";
    return "";
  };
  $("#log").innerHTML = text.split("\n").map((r) => {
    const t = r.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    const z = znacka(r);
    return z ? `<span class="${z}">${t}</span>` : t;
  }).join("\n");
}

const CISELNE = new Set([1, 2, 3, 4, 5]);          // sloupce zarovnane doprava

function kresliSouhrn(radky, ks, m2) {
  if (!radky.length) {
    $("#souhrn").innerHTML = '<p class="prazdno">Zatím není co objednávat — spusťte Převést.</p>';
    return;
  }
  const hlavy = ["Typ skla", "Tl.", "Šířka", "Výška", "Ks", "Plocha m²", "Pozice", "Poznámka"];
  const bunky = (r, tag) => r.map((v, i) =>
    `<${tag} class="${CISELNE.has(i) ? "cislo" : ""}">${v}</${tag}>`).join("");
  $("#souhrn").innerHTML = `<table>
    <thead><tr>${hlavy.map((h, i) =>
      `<th class="${CISELNE.has(i) ? "cislo" : ""}">${h}</th>`).join("")}</tr></thead>
    <tbody>${radky.map((r) =>
      `<tr class="${r[7].startsWith("NEPŘEPOČTENO") ? "overit" : ""}">${bunky(r, "td")}</tr>`).join("")}</tbody>
    <tfoot><tr>${bunky(["CELKEM", "", "", "", ks, m2, "", ""], "td")}</tr></tfoot>
  </table>`;
}

/* Texty z kusovniku jdou do HTML -- nazev profilu muze obsahovat cokoli. */
const esc = (t) => String(t).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* Vyber pozice -- stejny v zalozce Porovnani i v prohlizeci kusovniku. */
const tlacitkaPozic = () => stav.porovnani.map((x, i) => `
  <button class="poz" data-poz="${i}" aria-pressed="${i === stav.poz}"
          title="${esc(x.rozmer)}, ${x.kus} ks">poz. ${esc(x.pozice)}<span
    class="${x.zmen ? "" : "nic"}">${x.system === "Corona" ? "Corona" : x.zmen}</span></button>`).join("");

const jmenoSouboru = (cesta) => cesta.split(/[\\/]/).pop();

/* Original vlevo, vystup vpravo. Papir se zmensi, aby se vesel do pulky okna. */
async function otevriNahled() {
  const x = stav.porovnani[stav.poz];
  if (!x || UKAZKA) return;
  $("#prohlizec").hidden = false;
  $("#volba-nahled").innerHTML = tlacitkaPozic();
  $("#soubor-corona").textContent = jmenoSouboru(x.original);
  $("#system-nahled").textContent = x.system;
  $("#soubor-living").textContent = jmenoSouboru(x.vystup);
  const [a, b] = await Promise.all([api().nahled(x.original), api().nahled(x.vystup)]);
  $("#nahled-corona").innerHTML = a;
  $("#nahled-living").innerHTML = b;
  prizpusobPapir();
}

function prizpusobPapir() {
  document.querySelectorAll(".list").forEach((list) => {
    const papir = list.querySelector(".papir");
    if (papir) papir.style.zoom = Math.min(1, (list.clientWidth - 24) / (+papir.dataset.sirka + 64));
  });
}

/* Oba kusovniky maji stejne radky -- posun jednoho posune i druhy. */
["#nahled-corona", "#nahled-living"].forEach((id, i, oba) => $(id).addEventListener("scroll", (e) => {
  const druhy = $(oba[1 - i]);
  if (Math.abs(druhy.scrollTop - e.target.scrollTop) > 1) druhy.scrollTop = e.target.scrollTop;
}));
window.addEventListener("resize", prizpusobPapir);

/* Bez argumentu jen prekresli (jina pozice, prepinac "jen zmenene"). */
function kresliPorovnani(porovnani) {
  if (porovnani) {
    stav.porovnani = porovnani.sort((a, b) => a.pozice.localeCompare(b.pozice, "cs", { numeric: true }));
    stav.poz = Math.max(0, porovnani.findIndex((x) => x.zmen));   // prvni pozice se zmenou
  }
  const vse = stav.porovnani;
  if (!vse.length) {
    $("#volba").innerHTML = $("#poznamky").textContent = "";
    $("#porovnani").innerHTML = '<p class="prazdno">Porovnání Corona / LivIng se ukáže po převodu.</p>';
    return;
  }
  $("#volba").innerHTML = tlacitkaPozic();

  const x = vse[stav.poz];
  const radky = x.radky.filter((r) => r.zmena || !$("#jen-zmeny").checked);
  $("#poznamky").textContent = x.poznamky.join("  ·  ");
  const sloupce = [["Poř.", "cislo"], ["Kus", "cislo"], ["Art. Nr.", ""], ["Označení", ""],
                   ["Fe", ""], ["Corona", "cislo"], [x.system, "cislo"], ["Rozdíl", "cislo"]];
  $("#porovnani").innerHTML = `<table>
    <thead><tr>${sloupce.map(([h, t]) => `<th class="${t}">${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${radky.map((r) => `<tr class="${r.zmena ? "zmena" : ""}">
      <td class="cislo">${esc(r.c)}</td><td class="cislo">${esc(r.kus)}</td>
      <td>${esc(r.art)}</td><td class="nazev" title="${esc(r.nazev)}">${esc(r.nazev)}</td>
      <td>${esc(r.fe)}</td><td class="cislo puvodne">${esc(r.puvodne)}</td>
      <td class="cislo nove">${esc(r.nove)}</td><td class="cislo rozdil">${esc(r.rozdil)}</td>
    </tr>`).join("")}</tbody>
  </table>${radky.length ? "" : '<p class="prazdno">V této pozici se nic nemění.</p>'}`;
}

function nastavStav(text, klic) {
  $("#stav").className = "stav " + (klic || "");
  $("#stav-text").textContent = text;
}

function zalozka(id) {
  document.querySelectorAll(".zalozky button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.panel === id)));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("aktivni", p.id === id));
}

/* ---------- rezim ---------- */
function nastavRezim(tmavy) {
  document.documentElement.dataset.rezim = tmavy ? "tmavy" : "svetly";
  if (!UKAZKA) api().uloz_rezim(tmavy);
}

/* ---------- akce ---------- */
async function nactiSeznam() {
  stav.soubory = UKAZKA ? MOCK.seznam : await api().seznam($("#vstup").value);
  stav.vybrane = new Set(stav.soubory.map((f) => f.cesta));
  kresliSeznam();
}

async function prevest() {
  const vybrane = stav.soubory.filter((f) => stav.vybrane.has(f.cesta)).map((f) => f.cesta);
  if (UKAZKA) { nastavStav("Ukázková data — převod běží jen v aplikaci.", "varovna"); return; }
  nastavStav(`Převádím ${vybrane.length} kusovníků…`, "");
  const v = await api().prevest($("#vstup").value, $("#vystup").value, vybrane, [...stav.corona]);
  if (v.log !== undefined) kresliLog(v.log);
  if (v.radky) kresliSouhrn(v.radky, v.ks, v.m2);
  if (v.porovnani) kresliPorovnani(v.porovnani);
  nastavStav(v.stav, v.klic);
  if (v.zalozka) zalozka(v.zalozka);
}

/* ---------- prihlaseni udalosti ---------- */
document.addEventListener("click", async (e) => {
  const system = e.target.closest(".system");       // prepinac uvnitr radku, vyber nemeni
  if (system) {
    const c = decodeURIComponent(system.closest(".polozka").dataset.cesta);
    stav.corona.has(c) ? stav.corona.delete(c) : stav.corona.add(c);
    kresliSeznam();
    return;
  }
  const poz = e.target.closest(".poz");               // pozice v zalozce Porovnani
  if (poz) {
    stav.poz = +poz.dataset.poz; kresliPorovnani();
    if (!$("#prohlizec").hidden) otevriNahled();
    return;
  }
  const polozka = e.target.closest(".polozka");
  if (polozka) {
    const c = decodeURIComponent(polozka.dataset.cesta);
    stav.vybrane.has(c) ? stav.vybrane.delete(c) : stav.vybrane.add(c);
    kresliSeznam();
    return;
  }
  const zal = e.target.closest(".zalozky button");
  if (zal) { zalozka(zal.dataset.panel); return; }

  const proch = e.target.closest("[data-prochazet]");
  if (proch && !UKAZKA) {
    const pole = $("#" + proch.dataset.prochazet);
    const cesta = await api().prochazet(pole.value);
    if (cesta) { pole.value = cesta; if (pole.id === "vstup") nactiSeznam(); }
    return;
  }
  if (e.target.closest("#rezim")) {
    nastavRezim(document.documentElement.dataset.rezim !== "tmavy");
  } else if (e.target.closest("#vse")) {
    stav.vybrane = new Set(stav.soubory.map((f) => f.cesta)); kresliSeznam();
  } else if (e.target.closest("#nic")) {
    stav.vybrane.clear(); kresliSeznam();
  } else if (e.target.closest("#prevest")) {
    prevest();
  } else if (e.target.closest("#otevrit-nahled")) {
    otevriNahled();
  } else if (e.target.closest("#zavrit-nahled")) {
    $("#prohlizec").hidden = true;
  } else if (e.target.closest("#otevrit") && !UKAZKA) {
    const v = await api().otevri($("#vystup").value);
    if (!v.ok) nastavStav(v.hlaska, "varovna");
  }
});

$("#vstup").addEventListener("change", nactiSeznam);
$("#jen-zmeny").addEventListener("change", () => kresliPorovnani());
document.addEventListener("keydown", (e) => {
  if (!$("#prohlizec").hidden) {                   // v prohlizeci jen zavreni, prevod ne
    if (e.key === "Escape") $("#prohlizec").hidden = true;
    if (e.key === "F5") e.preventDefault();
    return;
  }
  if (e.key === "F5" || (e.key === "Enter" && e.target.tagName !== "BUTTON")) {
    e.preventDefault(); prevest();
  }
});

/* Pretazeni: zvyrazneni resi CSS, cesty dodava Python pres pywebviewFullPath. */
["dragenter", "dragover"].forEach((u) => document.addEventListener(u, (e) => {
  e.preventDefault(); document.body.classList.add("pretahuje");
}));
["dragleave", "drop"].forEach((u) => document.addEventListener(u, (e) => {
  if (u === "drop" || !e.relatedTarget) document.body.classList.remove("pretahuje");
}));

window.prijmiDropnute = function (soubory) {      // vola Python po dropu
  stav.soubory = soubory.seznam;
  soubory.nove.forEach((c) => stav.vybrane.add(c));
  if (soubory.vstup) $("#vstup").value = soubory.vstup;
  kresliSeznam();
  zalozka("p-vyber");
  if (soubory.hlaska) nastavStav(soubory.hlaska, "varovna");
};

async function start() {
  const z = UKAZKA ? MOCK.zaklad : await api().zaklad();
  $("#vstup").value = z.vstup;
  $("#vystup").value = z.vystup;
  document.documentElement.dataset.rezim = z.tmavy ? "tmavy" : "svetly";
  kresliOdecet(z.odecet);
  await nactiSeznam();
}

let spusteno = false;
function spustit() {
  if (spusteno) return;
  spusteno = true;
  UKAZKA = !window.pywebview;
  start();
}
window.addEventListener("pywebviewready", spustit, { once: true });
setTimeout(spustit, 700);        // v prohlizeci pywebviewready nikdy neprijde
