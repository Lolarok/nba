/* ============ NBA Advanced Stats — logica app ============ */
"use strict";

/* ---------------- Costanti e formule metriche ---------------- */
const METRICS = {
  pci: {
    label: "Pressure Creation Index", short: "PCI", color: "#ffb020",
    soft: "rgba(255,176,32,.12)",
    formula: "((Punti_PnR_BH + Punti_Iso + Punti_Creati_Assist) / (Poss_PnR_BH + Poss_Iso + Pass_Potenziali)) × (1 / Sec_Per_Tocco)",
    desc: "Misura la capacità di generare punteggio in possesso palla: quanti punti produce (o crea via passaggio) per canale primario P&R e isolamento, per tocco, normalizzato sulla velocità di decisione. Valori alti = giocatore che crea pressione constante sulla difesa.",
  },
  ogms: {
    label: "Off-Ball Gravity & Movement Score", short: "OGMS", color: "#2f9dff",
    soft: "rgba(47,157,255,.12)",
    formula: "(PPP_Medio_OffBall × Frequenza_Totale_OffBall) × Miglia_Attacco × (Punti_CaS / Tocchi)",
    desc: "Quantifica la gravità senza palla: quanto rende e quanto è usato nei Play Type off-ball (Spot-Up, Cut, Off-Screen), moltiplicato per il movimento in attacco (miglia percorse) e l'efficienza nel convertire i tocchi in punti catch-and-shoot.",
  },
  dadr: {
    label: "Defensive Activity & Deterrence Rate", short: "DADR", color: "#2ee6a8",
    soft: "rgba(46,230,168,.12)",
    formula: "((Tiri_Contestati + 1.5 × Deflections) / Minuti) × (1 − Diff_FG%_Concessa)",
    desc: "Combina attività difensiva (tiri contestati e deflectzioni per minuto) con deterrenza: il fattore (1 − Diff FG%) cresce quando il giocatore abbassa il FG% dei tiratori marcati rispetto alla loro media. Unito, misura l'impatto difensivo totale.",
  },
};
const PT_LABELS = { prbh: "Pick & Roll BH", iso: "Isolation", spotup: "Spot-Up", cut: "Cut", offscreen: "Off-Screen" };
const PT_KEYS = ["prbh", "iso", "spotup", "cut", "offscreen"];

/* Calcolo frontend delle 3 metriche: replica ESATTA delle formule.
   Usata sia sui dati demo sia come verifica dei dati prodotti dallo script Python. */
function computeMetrics(b) {
  const pt = b.playTypes, tr = b.tracking, adv = b.advanced;
  const pnrPts = pt.prbh.ppp * pt.prbh.poss;
  const isoPts = pt.iso.ppp * pt.iso.poss;
  const numP = pnrPts + isoPts + adv.ptsCreatedByAssist;
  const denP = pt.prbh.poss + pt.iso.poss + tr.potentialAssists;
  const pci = denP > 0 ? (numP / denP) * (1 / tr.secPerTouch) : 0;

  const offPoss = pt.spotup.poss + pt.cut.poss + pt.offscreen.poss;
  const offPts = pt.spotup.ppp * pt.spotup.poss + pt.cut.ppp * pt.cut.poss + pt.offscreen.ppp * pt.offscreen.poss;
  const pppOff = offPoss > 0 ? offPts / offPoss : 0;
  const freqOff = (pt.spotup.freq + pt.cut.freq + pt.offscreen.freq) / 100;
  const ogms = tr.touches > 0 ? pppOff * freqOff * tr.milesOff * (adv.catchShootPts / tr.touches) : 0;

  const dadr = b.min > 0 ? ((tr.contestedShots + 1.5 * tr.deflections) / b.min) * (1 - adv.diffFgPct) : 0;
  return { pci, ogms, dadr };
}

/* ---------------- Stato ---------------- */
const state = {
  data: null,
  period: "season",
  search: "",
  pos: "",
  team: "",
  sortKey: "m.pci",
  sortDir: -1,
};

/* ---------------- Utilità ---------------- */
const $ = (s) => document.querySelector(s);
const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "—" : v.toFixed(d));
const initials = (name) => name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
function teamColors(abbr) {
  const map = {
    DEN: "#fec408", OKC: "#ef3b24", LAL: "#fdb927", BOS: "#00a85a",
    SAS: "#8a8d8f", GSW: "#ffc72c", MIN: "#78be20", NYK: "#f58426",
    MIA: "#f9a11b", IND: "#fdbb30", PHI: "#006bb6", CLE: "#86003c",
    HOU: "#ce1141", DET: "#c8102e",
  };
  return map[abbr] || "#5d6b80";
}
function periodLabel(p) { return p === "season" ? "Stagione intera" : p === "l10" ? "Ultime 10 partite" : "Ultime 5 partite"; }
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

function tipHTML(k) {
  const m = METRICS[k];
  return `<div class="tip-body"><b>${m.label}</b><br>${m.desc}<span class="fm">${esc(m.formula)}</span></div>`;
}

/* ---------------- Inizializzazione ---------------- */
async function init() {
  buildHead2();
  try {
    const res = await fetch("data/nba_stats.json", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    state.data = await res.json();
  } catch {
    state.data = window.__DEMO_DATA__;  // fallback: dati incorporati nel build
  }
  if (!state.data) { $("#updatedTxt").textContent = "Dati non disponibili"; return; }

  fillTeamFilter();
  injectMetricTooltips();
  bindUI();
  renderAll();
}

function buildHead2() {
  const row = $("#headRow2");
  const cells = [];
  for (const k of PT_KEYS) {
    cells.push(`<th class="sortable" data-key="pt.${k}.ppp" data-type="num">PPP <span class="arrow"></span></th>`);
    cells.push(`<th class="sortable" data-key="pt.${k}.freq" data-type="num">Freq % <span class="arrow"></span></th>`);
  }
  const trk = [
    ["tr.touches", "Tocchi"], ["tr.secPerTouch", "Sec/tocco"], ["tr.potentialAssists", "Pass. pot."],
    ["tr.milesOff", "Miglia off."], ["tr.contestedShots", "Tiri contestati"], ["tr.deflections", "Deflections"],
  ];
  for (const [key, label] of trk) {
    cells.push(`<th class="sortable" data-key="${key}" data-type="num">${label} <span class="arrow"></span></th>`);
  }
  row.innerHTML = cells.join("");
}

function fillTeamFilter() {
  const teams = [...new Set(state.data.players.map(p => p.team))]
    .sort((a, b) => a.localeCompare(b, "it"));
  $("#teamFilter").innerHTML = `<option value="">Tutte le squadre</option>` +
    teams.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
}

function bindUI() {
  $("#searchInput").addEventListener("input", e => { state.search = e.target.value.trim().toLowerCase(); renderAll(); });
  $("#periodFilter").addEventListener("change", e => { state.period = e.target.value; renderAll(); });
  $("#posFilter").addEventListener("change", e => { state.pos = e.target.value; renderAll(); });
  $("#teamFilter").addEventListener("change", e => { state.team = e.target.value; renderAll(); });

  document.querySelectorAll("th.sortable").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.sortKey === key) state.sortDir *= -1;
      else { state.sortKey = key; state.sortDir = key === "name" || key === "teamAbbr" || key === "pos" ? 1 : -1; }
      renderTable();
    });
  });

  $("#overlay").addEventListener("click", closeDrawer);
  $("#drawerClose").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });
}

function renderAll() {
  renderUpdatedBadge();
  renderCards();
  renderTable();
}

/* ---------------- Badge aggiornamento ---------------- */
function renderUpdatedBadge() {
  const meta = state.data.meta;
  const d = new Date(meta.lastUpdated);
  const ok = !Number.isNaN(d.getTime());
  $("#updatedTxt").textContent = ok
    ? `Aggiornato: ${d.toLocaleDateString("it-IT", { day: "2-digit", month: "short" })} ${d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}${meta.source === "demo" ? " · dati demo" : ""}`
    : "—";
  $("#updatedBadge").classList.toggle("demo", meta.source === "demo");
}

/* ---------------- Card Top Performers ---------------- */
function renderCards() {
  const per = state.period;
  const players = state.data.players;
  const configs = [
    { k: "pci", c1: "#ffb020", c2: "#ff8a3d" },
    { k: "ogms", c1: "#2f9dff", c2: "#7bd3ff" },
    { k: "dadr", c1: "#2ee6a8", c2: "#9df5d4" },
  ];
  $("#tpPeriodLabel").textContent = periodLabel(per).toLowerCase();
  $("#cardsRow").innerHTML = configs.map(({ k, c1, c2 }) => {
    const m = METRICS[k];
    let best = null;
    for (const p of players) {
      const v = p.periods[per].metrics[k];
      if (!best || v > best.v) best = { p, v };
    }
    const prev = best.p.periods[per].metricsPrev[k];
    const delta = prev > 0 ? ((best.v - prev) / prev) * 100 : 0;
    const up = delta >= 0;
    const b = best.p.periods[per];
    return `
    <div class="tcard" data-id="${best.p.id}" style="--c1:${c1};--c2:${c2};--cs:${m.soft}">
      <span class="tag">★ ${m.short} — ${m.label}</span>
      <div class="prow">
        <div class="avatar">${esc(initials(best.p.name))}</div>
        <div>
          <div class="pname">${esc(best.p.name)}</div>
          <div class="pteam">${esc(best.p.team)} · ${best.p.pos}</div>
        </div>
      </div>
      <div class="big">${best.v.toFixed(3)} <small>${per === "season" ? "/ stagione" : per === "l10" ? "/ L10" : "/ L5"}</small></div>
      <span class="delta ${up ? "up" : "down"}">
        <svg viewBox="0 0 12 12" fill="currentColor"><path d="${up ? "M6 1l5 8H1z" : "M6 11L1 3h10z"}"/></svg>
        ${up ? "+" : ""}${delta.toFixed(1)}% vs settimana scorsa
      </span>
      <div class="foot">Leader NBA · ${b.gp} partite · ${fmt(b.min)} min/g · PTS <b>${fmt(b.pts)}</b> · AST <b>${fmt(b.ast)}</b></div>
    </div>`;
  }).join("");

  document.querySelectorAll(".tcard").forEach(c =>
    c.addEventListener("click", () => openDrawer(+c.dataset.id)));
}

/* ---------------- Tabella ---------------- */
function getSortedFiltered() {
  const { search, pos, team, period, sortKey, sortDir } = state;
  let rows = state.data.players.filter(p => {
    const b = p.periods[period];
    if (pos && p.pos !== pos) return false;
    if (team && p.team !== team) return false;
    if (search && !(p.name.toLowerCase().includes(search) || p.team.toLowerCase().includes(search) || p.teamAbbr.toLowerCase().includes(search))) return false;
    return true;
  });

  // risolvi la chiave di ordinamento su un valore piatto
  rows = rows.map(p => {
    const b = p.periods[period];
    const flat = {
      name: p.name, teamAbbr: p.teamAbbr, pos: p.pos,
      gp: b.gp, min: b.min, pts: b.pts, reb: b.reb, ast: b.ast, ts: b.ts,
      "m.pci": b.metrics.pci, "m.ogms": b.metrics.ogms, "m.dadr": b.metrics.dadr,
    };
    for (const k of PT_KEYS) { flat[`pt.${k}.ppp`] = b.playTypes[k].ppp; flat[`pt.${k}.freq`] = b.playTypes[k].freq; }
    flat["tr.touches"] = b.tracking.touches; flat["tr.secPerTouch"] = b.tracking.secPerTouch;
    flat["tr.potentialAssists"] = b.tracking.potentialAssists; flat["tr.milesOff"] = b.tracking.milesOff;
    flat["tr.contestedShots"] = b.tracking.contestedShots; flat["tr.deflections"] = b.tracking.deflections;
    return { p, b, v: flat[sortKey] ?? 0 };
  });

  const isStr = sortKey === "name" || sortKey === "teamAbbr" || sortKey === "pos";
  rows.sort((a, b2) => {
    const r = isStr ? String(a.v).localeCompare(String(b2.v), "it") : (a.v - b2.v);
    return r * sortDir;
  });
  return rows;
}

function renderTable() {
  const rows = getSortedFiltered();
  const maxPci = Math.max(...rows.map(r => r.b.metrics.pci), 0.001);

  $("#tbody").innerHTML = rows.map(({ p, b }) => {
    const pt = k => `
      <td>${b.playTypes[k].ppp.toFixed(2)}</td>
      <td>${b.playTypes[k].freq.toFixed(1)}</td>`;
    const tcol = teamColors(p.teamAbbr);
    return `
    <tr data-id="${p.id}">
      <td class="left"><div class="pl-cell"><span class="avatar">${esc(initials(p.name))}</span>
        <div><div class="nm">${esc(p.name)}</div><div class="ps">${p.pos} · GP ${b.gp}</div></div></div></td>
      <td class="left"><span class="team-cell"><span class="tav" style="background:${tcol}">${p.teamAbbr}</span>
        <span style="font-size:12px;color:var(--txt-1)">${esc(p.team.split(" ").slice(-1)[0])}</span></span></td>
      <td><span class="pos-pill">${p.pos}</span></td>
      <td>${b.gp}</td>
      <td>${fmt(b.min)}</td>
      <td style="font-weight:700">${fmt(b.pts)}</td>
      <td>${fmt(b.reb)}</td>
      <td>${fmt(b.ast)}</td>
      <td class="${b.ts >= 0.60 ? "good" : b.ts < 0.55 ? "bad" : ""}">${(b.ts * 100).toFixed(1)}</td>
      ${pt("prbh")}${pt("iso")}${pt("spotup")}${pt("cut")}${pt("offscreen")}
      <td>${fmt(b.tracking.touches)}</td>
      <td>${b.tracking.secPerTouch.toFixed(2)}</td>
      <td>${fmt(b.tracking.potentialAssists)}</td>
      <td>${b.tracking.milesOff.toFixed(2)}</td>
      <td>${fmt(b.tracking.contestedShots)}</td>
      <td>${fmt(b.tracking.deflections)}</td>
      <td class="met-pci"><span class="mval pci">${b.metrics.pci.toFixed(3)}</span><span class="bar-bg"><i style="width:${(b.metrics.pci / maxPci * 100).toFixed(0)}%"></i></span></td>
      <td class="met-ogms"><span class="mval ogms">${b.metrics.ogms.toFixed(3)}</span></td>
      <td class="met-dadr"><span class="mval dadr">${b.metrics.dadr.toFixed(3)}</span></td>
    </tr>`;
  }).join("") || `<tr><td colspan="30" style="text-align:center;padding:34px;color:var(--txt-2)">Nessun giocatore trovato — modifica i filtri.</td></tr>`;

  $("#rowCount").innerHTML = `Visualizzati <b>${rows.length}</b> giocatori su ${state.data.players.length} · ${periodLabel(state.period)} · ordinati per <b>${state.sortKey.startsWith("m.") ? METRICS[state.sortKey.slice(2)].short : esc(state.sortKey)}</b>`;

  // frecce di ordinamento
  document.querySelectorAll("th.sortable").forEach(th => {
    const arrow = th.querySelector(".arrow");
    if (th.dataset.key === state.sortKey) {
      th.classList.add("sorted");
      arrow.textContent = state.sortDir === 1 ? "▲" : "▼";
    } else { th.classList.remove("sorted"); arrow.textContent = ""; }
  });

  document.querySelectorAll("#tbody tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => openDrawer(+tr.dataset.id)));
}

/* Inietta una sola volta le icone tooltip sulle colonne metrica del thead */
function injectMetricTooltips() {
  document.querySelectorAll(".tip-ico-slot").forEach(slot => {
    const host = slot.closest(".tip-host");
    const th = host.closest("th");
    const metricKey = th?.dataset.key?.slice(2);
    if (metricKey && METRICS[metricKey]) {
      host.innerHTML = `${METRICS[metricKey].short}<svg class="tip-ico" viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="7.5" r=".5" fill="currentColor"/></svg>${tipHTML(metricKey)}`;
    }
  });
}

/* ---------------- Drawer profilo giocatore ---------------- */
let radarChart = null, ptChart = null;

function openDrawer(id) {
  const p = state.data.players.find(x => x.id === id);
  if (!p) return;
  const per = state.period;
  const b = p.periods[per];
  const tcol = teamColors(p.teamAbbr);

  $("#drWho").innerHTML = `
    <div class="avatar">${esc(initials(p.name))}</div>
    <div>
      <div class="nm">${esc(p.name)}</div>
      <div class="tm"><span class="tav" style="background:${tcol};color:#10141b">${p.teamAbbr}</span> ${esc(p.team)} · ${p.pos}</div>
    </div>`;

  const stats = [
    ["GP", b.gp, ""], ["MIN", fmt(b.min), ""], ["PTS", fmt(b.pts), ""],
    ["REB", fmt(b.reb), ""], ["AST", fmt(b.ast), ""], ["TS%", (b.ts * 100).toFixed(1), ""],
    ["Tocchi", fmt(b.tracking.touches), ""], ["Sec/tocco", b.tracking.secPerTouch.toFixed(2), ""],
    ["Pass. pot.", fmt(b.tracking.potentialAssists), ""], ["Miglia off.", b.tracking.milesOff.toFixed(2), ""],
    ["Tiri contest.", fmt(b.tracking.contestedShots), ""], ["Deflections", fmt(b.tracking.deflections), ""],
  ];

  const mets = ["pci", "ogms", "dadr"].map(k => {
    const m = b.metrics[k], prev = b.periods?.[per]?.metricsPrev?.[k];
    return `<div class="dr-stat"><div class="v ${k}">${m.toFixed(3)}</div><div class="k">${METRICS[k].short}</div></div>`;
  }).join("");

  $("#drBody").innerHTML = `
    <div class="dr-sec">
      <h3>Statistiche — ${periodLabel(per)}</h3>
      <div class="dr-stats">${stats.map(([k, v]) => `<div class="dr-stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("")}</div>
    </div>
    <div class="dr-sec">
      <h3>Metriche proprietarie</h3>
      <div class="dr-metrics">${mets}</div>
      <div class="dr-note">Valori calcolati con le formule ufficiali PCI · OGMS · DADR sul periodo selezionato. Passa il mouse sulle intestazioni della tabella per la formula completa.</div>
    </div>
    <div class="dr-sec">
      <h3>Metriche vs media NBA</h3>
      <div class="chart-box"><canvas id="radarCanvas"></canvas></div>
    </div>
    <div class="dr-sec">
      <h3>Distribuzione Play Type</h3>
      <div class="chart-box"><canvas id="ptCanvas"></canvas></div>
      <div class="dr-note">Frequenza % dei possessi per ciascun Play Type Synergy nel periodo selezionato.</div>
    </div>`;

  $("#drawer").classList.add("on");
  $("#overlay").classList.add("on");
  $("#drawer").setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  drawRadar(p, per);
  drawPtChart(p, per);
}

function closeDrawer() {
  $("#drawer").classList.remove("on");
  $("#overlay").classList.remove("on");
  $("#drawer").setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  if (radarChart) { radarChart.destroy(); radarChart = null; }
  if (ptChart) { ptChart.destroy(); ptChart = null; }
}

function drawRadar(p, per) {
  const avg = state.data.meta.leagueAverages[per];
  const keys = ["pci", "ogms", "dadr"];
  const player = p.periods[per].metrics;
  // normalizza rispetto alla media (1.0 = media NBA), scala fino a 2x
  const norm = v => Math.min(2, v);
  const data = {
    labels: keys.map(k => METRICS[k].short),
    datasets: [
      {
        label: p.name.split(" ").slice(-1)[0],
        data: keys.map(k => norm(player[k] / avg[k])),
        borderColor: "#ffb020", backgroundColor: "rgba(255,176,32,.18)",
        pointBackgroundColor: "#ffb020", pointRadius: 4, borderWidth: 2,
      },
      {
        label: "Media NBA (1.0)",
        data: [1, 1, 1],
        borderColor: "#5d6b80", backgroundColor: "rgba(93,107,128,.10)",
        pointBackgroundColor: "#5d6b80", pointRadius: 3, borderWidth: 1.5, borderDash: [5, 4],
      },
    ],
  };
  const css = getComputedStyle(document.documentElement);
  const txt = css.getPropertyValue("--txt-1").trim();
  radarChart = new Chart($("#radarCanvas"), {
    type: "radar",
    data,
    options: {
      responsive: true, maintainAspectRatio: true, aspectRatio: 1.35,
      plugins: {
        legend: { labels: { color: txt, font: { size: 11 }, boxWidth: 14 } },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(2)}× media` } },
      },
      scales: {
        r: {
          min: 0, max: 2,
          ticks: { color: txt, backdropColor: "transparent", stepSize: 0.5, font: { size: 9 } },
          grid: { color: "rgba(93,107,128,.25)" }, angleLines: { color: "rgba(93,107,128,.25)" },
          pointLabels: { color: txt, font: { size: 11, weight: 700 } },
        },
      },
    },
  });
}

function drawPtChart(p, per) {
  const b = p.periods[per];
  const colors = { prbh: "#ffb020", iso: "#ff8a3d", spotup: "#2f9dff", cut: "#2ee6a8", offscreen: "#9df5d4" };
  ptChart = new Chart($("#ptCanvas"), {
    type: "bar",
    data: {
      labels: PT_KEYS.map(k => PT_LABELS[k]),
      datasets: [
        { label: "Frequenza %", data: PT_KEYS.map(k => b.playTypes[k].freq), backgroundColor: PT_KEYS.map(k => colors[k]), borderRadius: 6, yAxisID: "y" },
        { label: "PPP", data: PT_KEYS.map(k => b.playTypes[k].ppp), type: "line", borderColor: "#e8edf5", backgroundColor: "#e8edf5", borderWidth: 2, pointRadius: 4, yAxisID: "y2", tension: .25 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: true, aspectRatio: 1.5,
      plugins: { legend: { labels: { color: "#9aa7ba", font: { size: 11 }, boxWidth: 14 } } },
      scales: {
        x: { ticks: { color: "#9aa7ba", font: { size: 10 } }, grid: { display: false } },
        y: { position: "left", title: { display: true, text: "Freq %", color: "#5d6b80", font: { size: 10 } }, ticks: { color: "#9aa7ba", font: { size: 10 } }, grid: { color: "rgba(93,107,128,.18)" } },
        y2: { position: "right", min: 0.7, max: 1.5, title: { display: true, text: "PPP", color: "#5d6b80", font: { size: 10 } }, ticks: { color: "#9aa7ba", font: { size: 10 }, stepSize: 0.2 }, grid: { display: false } },
      },
    },
  });
}

init();
