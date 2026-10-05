"use strict";

const runnerId = Number(new URLSearchParams(location.search).get("runner"));
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function render(data) {
  $("class-name").textContent = data.class;
  $("runner-name").textContent = data.name;
  const status = $("status");
  status.textContent = data.status;
  status.className = data.state;
  const percentage = data.progress.total ? (data.progress.passed / data.progress.total) * 100 : 0;
  $("content").innerHTML = `
    <section class="profile-card">
      <div class="org">${esc(data.org)}</div>
      <div class="summary">
        <div><span>Start</span><strong>${esc(data.start || "–")}</strong></div>
        <div><span>Zeit</span><strong>${esc(data.time || "–")}</strong></div>
        <div><span>Letzter Funkposten</span><strong>${esc(data.latest)}</strong></div>
        <div><span>Startnummer</span><strong>${esc(data.bib || "–")}</strong></div>
      </div>
      <div class="progress-label">Funkposten: ${data.progress.passed} / ${data.progress.total}</div>
      <div class="progress"><div style="width:${percentage}%"></div></div>
    </section>
    <section class="splits">
      <h2>Zwischenzeiten</h2>
      <table><thead><tr><th>Funkposten</th><th class="r">Zeit</th><th class="r">Rang</th></tr></thead>
      <tbody>${data.controls.map((control) => `<tr class="${control.passed ? "passed" : "pending"}">
        <td><span class="marker"></span>${esc(control.name)}</td>
        <td class="r">${esc(control.time || "–")}</td>
        <td class="r rank">${control.rank ? `${control.rank}.` : "–"}</td>
      </tr>`).join("") || '<tr><td colspan="3">Für diese Strecke sind keine Funkposten hinterlegt.</td></tr>'}</tbody></table>
    </section>`;
}

async function refresh() {
  if (!runnerId) {
    $("content").innerHTML = '<div class="empty">In der URL fehlt der Läufer: ?runner=&lt;ID&gt;</div>';
    return;
  }
  try {
    const response = await fetch(`/api/runner/${runnerId}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    render(await response.json());
  } catch {
    $("content").innerHTML = '<div class="empty">Läufer nicht gefunden oder keine Datenverbindung.</div>';
  }
}

refresh();
setInterval(refresh, 2000);
