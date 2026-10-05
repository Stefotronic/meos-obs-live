"use strict";

const classId = Number(new URLSearchParams(location.search).get("class"));
const topParameter = new URLSearchParams(location.search).get("top");
const $ = (id) => document.getElementById(id);
let shown = new Set();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function medal(place) {
  return ["🥇", "🥈", "🥉"][place - 1] || "";
}

function winnerCard(item, revealed) {
  if (!revealed.has(item.place)) {
    return `<article class="winner pending place-${item.place}"><div>Platz ${item.place} wird enthüllt</div></article>`;
  }
  const marker = medal(item.place);
  return `<article class="winner place-${item.place} ${shown.has(item.place) ? "" : "reveal"}">
    ${marker ? `<div class="medal">${marker}</div>` : ""}
    <div class="place">${item.place}. Platz</div>
    <h2>${esc(item.name)}</h2>
    <div class="time">${esc(item.time)}${item.behind ? `<span>${esc(item.behind)}</span>` : ""}</div>
  </article>`;
}

function render(data) {
  const topLimit = topParameter === "3" || topParameter === "6" ? Number(topParameter) : data.top_limit || 6;
  $("class-name").textContent = `Klasse · ${data.class}`;
  $("podium-title").textContent = `Sieger · Top ${topLimit}`;
  const placed = data.places.filter((item) => item.place <= topLimit);
  $("status").textContent = placed.length >= topLimit ? `Top ${topLimit} vollständig` : `${placed.length} von ${topLimit} Plätzen entschieden`;
  const revealed = new Set(data.revealed || []);
  const byPlace = new Map(data.places.map((item) => [item.place, item]));
  const card = (place) => winnerCard(byPlace.get(place) || { place }, revealed);
  $("content").innerHTML = `<section class="podium">
    <div class="top-three">${[2, 1, 3].map(card).join("")}</div>
    ${topLimit === 6 ? `<div class="other-places">${[4, 5, 6].map(card).join("")}</div>` : ""}
  </section>`;
  shown = revealed;
}

async function refresh() {
  if (!classId) {
    $("content").innerHTML = '<div class="empty">In der URL fehlt die Klasse: ?class=&lt;ID&gt;</div>';
    return;
  }
  try {
    const response = await fetch(`/api/podium/${classId}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    render(await response.json());
  } catch {
    $("content").innerHTML = '<div class="empty">Klasse nicht gefunden oder keine Datenverbindung.</div>';
  }
}

refresh();
setInterval(refresh, 2000);