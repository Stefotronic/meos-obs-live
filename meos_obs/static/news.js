"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function eventCard(item) {
    const finish = item.kind === "finish";
    const highlight = item.highlight === "best" || item.highlight === "top3" ? item.highlight : "";
    const badge = item.highlight_label
      ? `<span class="highlight ${highlight}">${esc(item.highlight_label)}</span>`
      : "";
    return `<article class="event ${esc(item.kind)} ${highlight}">
      <div class="icon">${finish ? "✓" : "●"}</div>
      <div class="title">${esc(item.title)}${badge}</div>
      <div><div class="name">${esc(item.name)}</div>
      <div class="meta">${esc(item.class)} · ${esc(item.org)}</div></div>
      <div class="time">${esc(item.detail || "–")}<span>${esc(item.status || `gemeldet ${item.reported_at}`)}</span></div>
    </article>`;
}

function category(kind, title, items) {
  const empty = kind === "finish" ? "Noch keine Zieleinläufe." : "Noch keine Funkposten-Durchgänge.";
  return `<section class="category ${kind}">
    <h2>${title} · ${items.length}</h2>
    <div class="event-list">${items.length ? items.map(eventCard).join("") : `<div class="empty">${empty}</div>`}</div>
  </section>`;
}

function render(items) {
  const finishers = items.filter((item) => item.kind === "finish").slice(0, 5);
  const radios = items.filter((item) => item.kind === "radio").slice(0, 5);
  $("feed").innerHTML = category("finish", "Neu im Ziel", finishers)
    + category("radio", "Neue Funkposten", radios);
}

async function refresh() {
  try {
    const [news, status] = await Promise.all([
      fetch("/api/news?limit=50", { cache: "no-store" }).then((response) => response.json()),
      fetch("/api/status", { cache: "no-store" }).then((response) => response.json()),
    ]);
    $("competition").textContent = status.competition.name || "Live-Ticker";
    $("status").textContent = news.length ? `${news.length} aktuelle Meldungen` : "Warte auf Daten";
    render(news);
  } catch {
    $("status").textContent = "Keine Datenverbindung";
  }
}

refresh();
setInterval(refresh, 2000);
