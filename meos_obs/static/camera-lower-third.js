"use strict";

const params = new URLSearchParams(location.search);
const classId = Number(params.get("class"));
const controlId = Number(params.get("control"));
const always = params.get("always") === "1";
const demo = params.get("demo") === "1";
const duration = Math.max(3, Number(params.get("duration")) || 20) * 1000;
const root = document.getElementById("lower-third");
const demoStartPlace = Math.min(58, Math.max(2, Number(params.get("start")) || 2));
let initialized = false;
let eventKey = "";
let hideTimer;
const demoStarted = Date.now();

function demoRow(place) {
  const seconds = 20 * 60 + 14 + (place - 1) * 19;
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  const behind = (place - 1) * 19;
  return {
    place,
    team: `Staffel ${String(place).padStart(2, "0")}`,
    runner: `Läufer:in ${String(place).padStart(2, "0")}`,
    time: `${minutes}:${remainder}`,
    behind: place === 1 ? "" : `+${Math.floor(behind / 60)}:${String(behind % 60).padStart(2, "0")}`,
  };
}

function demoData() {
  // Alle zwei Sekunden wandert das Dreierfenster von 2–4 bis 58–60 und
  // beginnt danach wieder vorne. Platz 1 bleibt durchgehend sichtbar.
  const firstPlace = 2 + (demoStartPlace - 2 + Math.floor((Date.now() - demoStarted) / 2000)) % 57;
  const standings = [firstPlace, firstPlace + 1, firstPlace + 2].map(demoRow);
  return {
    class: "Deutschland-Cup · Demo mit 60 Staffeln",
    control: "56",
    leader: [demoRow(1)],
    standings,
    latest: { ...standings[2], leg: 2, legs: 5, seen: `demo-${firstPlace}` },
  };
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function show() {
  root.classList.add("visible");
  clearTimeout(hideTimer);
  if (!always) hideTimer = setTimeout(() => root.classList.remove("visible"), duration);
}

function render(data) {
  const rows = [...(data.leader || []), ...data.standings];
  const standings = rows.map((row, index) => `<div class="standing">
    <div class="place">${row.place}.</div><div><div class="team">${esc(row.team)}</div><div class="org">${esc(row.runner)}</div></div>
    <div class="time">${esc(index === 0 ? row.time : row.behind)}</div></div>`).join("");
  const latest = data.latest ? `<div class="latest"><b>Gerade durch</b><span class="runner">${esc(data.latest.runner)}</span><span>${esc(data.latest.team)}</span><span class="place-now">Platz ${esc(data.latest.place)}</span></div>` : "";
  root.innerHTML = `<section class="panel"><div class="headline"><strong>${esc(data.class)}</strong><span>Funkposten ${esc(data.control)}</span></div>${standings || '<div class="empty">Noch keine Durchgänge</div>'}${latest}</section>`;
}

async function refresh() {
  if (demo) {
    render(demoData());
    show();
    return;
  }
  if (!classId || !controlId) return;
  try {
    const response = await fetch(`/api/camera-lower-third/${classId}/${controlId}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    const data = await response.json();
    render(data);
    const nextKey = data.latest ? `${data.latest.runner}:${data.latest.seen}` : "";
    if (always || (initialized && nextKey && nextKey !== eventKey)) show();
    eventKey = nextKey;
    initialized = true;
  } catch {
    root.innerHTML = '<section class="panel"><div class="empty">Keine Datenverbindung</div></section>';
  }
}

refresh();
setInterval(refresh, 1000);