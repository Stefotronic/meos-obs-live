"use strict";

const runnerId = Number(new URLSearchParams(location.search).get("runner"));
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function splitCell(split) {
  if (!split.time) return '<div class="split empty-split">–</div>';
  const rank = split.rank ? `<span class="rank">${split.rank}.</span>` : "";
  const behind = split.behind ? `<span class="behind">${esc(split.behind)}</span>` : '<span class="best">führt</span>';
  return `<div class="split"><b>${esc(split.time)}</b>${rank}${behind}</div>`;
}

function render(data) {
  $("class-name").textContent = `Klasse · ${data.class}`;
  $("title").textContent = `${data.selected_name} gegen die Spitzengruppe`;
  $("status").textContent = `${data.athletes.length} Läufer im Vergleich`;
  $("content").style.setProperty("--columns", String(Math.max(data.athletes.length, 1)));
  const athletes = data.athletes.map((athlete) => `<section class="athlete ${athlete.selected ? "selected" : ""}">
    <div class="athlete-top">${athlete.selected ? "AUSGEWÄHLT" : `TOP ${athlete.leader_position || "–"}`}</div>
    <h2>${esc(athlete.name)}</h2>
    <div class="org">${esc(athlete.org)}</div>
    <div class="athlete-status">${esc(athlete.status)}</div>
    ${athlete.finish_time ? `<div class="finish">${esc(athlete.finish_time)} <span>Platz ${athlete.finish_rank}</span></div>` : ""}
  </section>`).join("");
  const rows = data.controls.map((control, index) => `<div class="comparison-row">
    <div class="control">Funkposten <b>${esc(control.name)}</b></div>
    ${data.athletes.map((athlete) => `<div class="split-column ${athlete.selected ? "selected" : ""}">${splitCell(athlete.splits[index])}</div>`).join("")}
  </div>`).join("");
  $("content").innerHTML = `<section class="comparison">
    <div class="comparison-row comparison-head"><div class="corner">FUNKPOSTEN</div>${athletes}</div>
    ${rows || '<div class="no-controls">Noch keine Funkposten-Daten verfügbar.</div>'}
  </section>`;
}

async function refresh() {
  if (!runnerId) {
    $("content").innerHTML = '<div class="empty">In der URL fehlt der Läufer: ?runner=&lt;ID&gt;</div>';
    return;
  }
  try {
    const response = await fetch(`/api/head-to-head/${runnerId}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    render(await response.json());
  } catch {
    $("content").innerHTML = '<div class="empty">Direktvergleich nicht verfügbar. Es werden Einzelklassen unterstützt.</div>';
  }
}

refresh();
setInterval(refresh, 2000);