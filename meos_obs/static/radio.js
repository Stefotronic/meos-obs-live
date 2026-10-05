"use strict";

const params = new URLSearchParams(location.search);
const classId = Number(params.get("class"));
const controlId = Number(params.get("control"));
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function row(item, passed) {
  return `<tr>
    <td class="place">${passed && item.rank ? `${item.rank}.` : ""}</td>
    <td><b>${esc(item.name)}</b><div class="org">${esc(item.org)}</div></td>
    <td class="r">${passed ? esc(item.time) : `<span class="status">${esc(item.status)}</span>`}</td>
    <td class="r detail">${passed ? `${esc(item.progress)} Posten` : `zuletzt: ${esc(item.last)}`}</td>
  </tr>`;
}

function render(data) {
  $("class-name").textContent = data.class;
  $("control-name").textContent = `Funkposten ${data.control}`;
  $("status").textContent = `${data.passed.length} von ${data.total} durch`;
  $("content").innerHTML = `
    <section class="panel passed">
      <h2>Bereits durch · ${data.passed.length}</h2>
      <table><thead><tr><th>Pl.</th><th>Läufer</th><th class="r">Zeit</th><th class="r">Fortschritt</th></tr></thead>
      <tbody>${data.passed.map((item) => row(item, true)).join("") || '<tr><td colspan="4">Noch kein Durchgang.</td></tr>'}</tbody></table>
    </section>
    <section class="panel open">
      <h2>Noch offen · ${data.open.length}</h2>
      <table><thead><tr><th></th><th>Läufer</th><th class="r">Status</th><th class="r">Letzter Funkposten</th></tr></thead>
      <tbody>${data.open.map((item) => row(item, false)).join("") || '<tr><td colspan="4">Alle Läufer sind durch.</td></tr>'}</tbody></table>
    </section>`;
}

async function refresh() {
  if (!classId || !controlId) {
    $("content").innerHTML = '<div class="empty">In der URL fehlen Klasse oder Funkposten.</div>';
    return;
  }
  try {
    const response = await fetch(`/api/radio/${classId}/${controlId}`, { cache: "no-store" });
    if (!response.ok) throw new Error();
    render(await response.json());
  } catch {
    $("content").innerHTML = '<div class="empty">Funkposten oder Klasse nicht gefunden.</div>';
  }
}

refresh();
setInterval(refresh, 2000);
