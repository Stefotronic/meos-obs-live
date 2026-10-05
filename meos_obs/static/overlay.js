"use strict";

// URL-Parameter (optional):
//   ?class=<id>        feste Klasse, ignoriert die Regie
//   ?ticker=0|1        Ticker erzwingen/ausblenden
//   ?transparent=1     transparenter Hintergrund
const params = new URLSearchParams(location.search);
const URL_CLASS = params.get("class") ? Number(params.get("class")) : null;
const URL_TICKER = params.get("ticker");
if (params.get("transparent") === "1") document.body.classList.add("transparent");

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let config = null;
let classes = [];
let data = null;
let classId = null;
let page = 0;
let pages = 1;
let pageStart = Date.now();
let lastSkip = null;
let lastReport = "";
let busy = false;
let pending = false;

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function targetFixed() {
  if (URL_CLASS != null) return URL_CLASS;
  return config && config.mode === "fixed" ? config.fixed_class : null;
}

function rotationList() {
  let list = classes;
  if (config.rotate_classes.length) list = list.filter((c) => config.rotate_classes.includes(c.id));
  else if (config.hide_empty) list = list.filter((c) => c.active);
  if (!list.length) list = classes.filter((c) => c.entries > 0);
  return list.map((c) => c.id);
}

function setClass(id) {
  if (id === classId) return;
  classId = id;
  page = 0;
  pageStart = Date.now();
}

function nextClass() {
  const list = rotationList();
  if (!list.length) return setClass(null);
  const i = list.indexOf(classId);
  setClass(list[(i + 1) % list.length]);
  page = 0;
  pageStart = Date.now();
}

function advance() {
  if (page + 1 < pages) {
    page++;
    pageStart = Date.now();
    render();
    return;
  }
  page = 0;
  pageStart = Date.now();
  if (targetFixed() == null) nextClass();
  refresh();
}

async function refresh() {
  if (busy) { pending = true; return; }
  busy = true;
  try {
    const [disp, cls, status] = await Promise.all([
      getJSON("/api/display"), getJSON("/api/classes"), getJSON("/api/status"),
    ]);
    config = disp.config;
    classes = cls;
    $("cmp-name").textContent = status.competition.name || "";
    const age = status.meos.age ?? 999;
    $("conn").classList.toggle("stale", !status.meos.connected || age > 15);

    if (lastSkip !== null && config.skip_counter !== lastSkip && targetFixed() == null) nextClass();
    lastSkip = config.skip_counter;

    const fixed = targetFixed();
    if (fixed != null) setClass(fixed);
    else if (classId == null || !rotationList().includes(classId)) nextClass();

    data = classId != null ? await getJSON(`/api/class/${classId}`) : null;

    // Staffeln benötigen die komplette Breite für alle Strecken und die
    // Gesamtzeit. Der Ticker kann bei Bedarf weiterhin mit ?ticker=1
    // ausdrücklich eingeschaltet werden.
    const showTicker = URL_TICKER != null
      ? URL_TICKER !== "0"
      : config.show_ticker && data?.type !== "team";
    document.body.classList.toggle("no-ticker", !showTicker);
    const tickerItems = await getJSON(`/api/ticker?limit=${config.ticker_count}`);
    if (showTicker) renderTicker(tickerItems);

    // Kein automatischer Zieleinlauf-Ticker bei Staffeln: Er würde die erste
    // Ergebniszeile überdecken.
    document.body.classList.remove("team-finish-ticker");

    render();
  } catch (e) {
    console.error(e);
    $("conn").classList.add("stale");
  } finally {
    busy = false;
    if (pending) { pending = false; refresh(); }
  }
}

function indHead(d) {
  const ctrls = d.controls.map((c) => `<th class="r">${esc(c.name)}</th>`).join("");
  return `<tr><th class="r">Pl.</th><th>Name</th><th>Verein</th>${ctrls}<th class="r">Zeit</th><th class="r">Rückst.</th></tr>`;
}

function statusCell(r) {
  // einzeilig halten, damit die Zeilenhöhe konstant bleibt
  const text = r.info || [r.status, r.time].filter(Boolean).join(" ");
  return `<td class="status" colspan="2" style="text-align:right">${esc(text)}</td>`;
}

function indRow(r) {
  const splits = r.splits.map((s) =>
    `<td class="split${s.best ? " best" : ""}">${esc(s.time)}${s.rank ? `<span class="rk">(${s.rank})</span>` : ""}</td>`).join("");
  const timeCells = r.state === "finished"
    ? `<td class="time">${esc(r.time)}</td><td class="behind">${esc(r.behind)}</td>`
    : statusCell(r);
  return `<tr class="${r.state}${r.new ? " new" : ""}">
    <td class="place${r.provisional_place ? " provisional" : ""}">${r.place ? r.place + "." : r.provisional_place ? r.provisional_place + "." : ""}</td>
    <td class="name">${esc(r.name)}</td>
    <td class="org">${esc(r.org)}</td>${splits}${timeCells}</tr>`;
}

function teamHead(d) {
  let legs = "";
  for (let i = 1; i <= d.legs; i++) legs += `<th class="leg-col">Strecke ${i}</th>`;
  return `<tr><th class="r place-col">Pl.</th><th class="team-col">Team</th>${legs}<th class="r total-col">Gesamtzeit</th></tr>`;
}

function legLine(l) {
  if (l.state === "finished") {
    return `${esc(l.time)}${l.rank ? ` (${l.rank})` : ""}`;
  }
  return esc(l.time);
}

function teamRow(r) {
  const legs = r.legs.map((l) =>
    `<td class="leg ${l.state}${l.new ? " new" : ""}"><span class="ln">${esc(l.name)}</span><span class="lt">${legLine(l)}</span></td>`).join("");
  const timeCell = r.state === "finished" || r.time
    ? `<td class="time">${esc(r.time)}</td>`
    : `<td class="status" style="text-align:right">${esc(r.info || r.status)}</td>`;
  return `<tr class="${r.state}">
    <td class="place${r.provisional_place ? " provisional" : ""}">${r.place ? r.place + "." : r.provisional_place ? r.provisional_place + "." : ""}</td>
    <td class="name">${esc(r.name)}</td>${legs}${timeCell}</tr>`;
}

function render() {
  const table = $("res-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  if (!data || data.id !== classId) {
    $("cls-name").textContent = "";
    $("cls-meta").textContent = "";
    thead.innerHTML = "";
    tbody.innerHTML = "";
    $("empty").hidden = false;
    return;
  }

  const isTeam = data.type === "team";
  table.className = data.type;
  $("cls-name").textContent = data.name;
  thead.innerHTML = isTeam ? teamHead(data) : indHead(data);

  const rowH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--row-h")) * (isTeam ? 1.45 : 1);
  const box = $("results");
  const avail = box.clientHeight - thead.offsetHeight - 16;
  let perPage = Math.max(1, Math.floor(avail / rowH));
  const draw = () => {
    pages = Math.max(1, Math.ceil(data.rows.length / perPage));
    if (page >= pages) { page = 0; pageStart = Date.now(); }
    const slice = data.rows.slice(page * perPage, (page + 1) * perPage);
    tbody.innerHTML = slice.map(isTeam ? teamRow : indRow).join("");
  };
  draw();
  // Falls Zeilen doch höher sind als erwartet: so lange verkleinern, bis alles passt
  while (perPage > 1 && box.scrollHeight > box.clientHeight) {
    perPage--;
    draw();
  }
  $("empty").hidden = data.rows.length > 0;

  const c = data.counts;
  const meta = [`${c.finished} im Ziel`, `${c.running} ${isTeam ? "unterwegs" : "im Wald"}`];
  if (data.length) meta.push(`${(data.length / 1000).toFixed(1).replace(".", ",")} km`);
  if (pages > 1) meta.push(`Seite ${page + 1}/${pages}`);
  $("cls-meta").textContent = meta.join(" · ");

  report();
}

function renderTicker(items) {
  const list = $("ticker-list");
  list.innerHTML = items.map((t) => `
    <li class="${t.new ? "new" : ""}">
      <div class="t-name">${esc(t.name)}</div>
      <div class="t-time">${esc(t.status || t.time)}</div>
      <div class="t-sub">${esc(t.class)} · ${esc(t.team || t.org)}</div>
      <div class="t-place">${t.place ? t.place + "." : ""}</div>
    </li>`).join("");
  if (!document.body.classList.contains("team-finish-ticker")) {
    const box = $("ticker");
    while (list.lastElementChild && box.scrollHeight > box.clientHeight) list.lastElementChild.remove();
  }
}

function report() {
  const view = { class_id: classId, class_name: data && data.id === classId ? data.name : "", page: page + 1, pages };
  const key = JSON.stringify(view);
  if (key === lastReport) return;
  lastReport = key;
  fetch("/api/display/current", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: key,
  }).catch(() => {});
}

function tick() {
  const now = new Date();
  $("clock").textContent = now.toLocaleTimeString("de-DE");
  if (!config) return;
  const dur = config.page_seconds * 1000;
  const elapsed = Date.now() - pageStart;
  $("progress-bar").style.width = `${Math.min(100, (elapsed / dur) * 100)}%`;
  if (elapsed >= dur) advance();
}

refresh();
setInterval(refresh, 2000);
setInterval(tick, 250);
