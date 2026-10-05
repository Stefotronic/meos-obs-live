"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let config = null;
let specialClassId = null;
let allClasses = [];
let availableControls = [];

async function api(url, body) {
  const opts = body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function update(patch) {
  await api("/api/display", patch);
  await refresh();
}

function setOptions(id, options, value, placeholder) {
  const el = $(id);
  const old = String(value ?? el.value);
  el.innerHTML = `${placeholder ? `<option value="">${placeholder}</option>` : ""}${options.map((option) =>
    `<option value="${option.id}">${esc(option.name)}</option>`).join("")}`;
  el.value = options.some((option) => String(option.id) === old) ? old : "";
}

async function refreshSpecialViews(classes) {
  setOptions("special-class", classes, specialClassId, "Klasse wählen");
  specialClassId = Number($("special-class").value) || null;
  if (!specialClassId) {
    setOptions("special-runner", [], null, "Läufer wählen");
    setOptions("special-control", availableControls, $("special-control").value, "Funkposten wählen");
    $("runner-url").textContent = "Klasse und Läufer wählen";
    $("head-to-head-url").textContent = "Klasse und Läufer wählen";
    $("podium-url").textContent = "Klasse wählen";
    $("radio-url").textContent = "Klasse wählen";
    $("camera-lower-third-url").textContent = "Staffelklasse und Funkposten wählen";
    return;
  }
  const [runners, controls, podiumMode] = await Promise.all([
    api(`/api/class/${specialClassId}/runners`), api(`/api/class/${specialClassId}/controls`), api(`/api/podium/mode/${specialClassId}`),
  ]);
  setOptions("special-runner", runners, $("special-runner").value, "Läufer wählen");
  availableControls = controls.controls;
  setOptions("special-control", availableControls, $("special-control").value, "Funkposten wählen");
  $("podium-limit").value = String(podiumMode.top);
  updateSpecialUrls();
}

function updateSpecialUrls() {
  const runner = $("special-runner").value;
  const control = $("special-control").value;
  const podiumLimit = Number($("podium-limit").value);
  document.querySelectorAll("[data-podium-place]").forEach((button) => {
    button.hidden = podiumLimit === 3 && Number(button.dataset.podiumPlace) > 3;
  });
  $("runner-url").textContent = runner ? `${location.origin}/runner?runner=${runner}` : "Läufer wählen";
  $("head-to-head-url").textContent = runner ? `${location.origin}/head-to-head?runner=${runner}` : "Läufer wählen";
  $("podium-url").textContent = specialClassId ? `${location.origin}/podium?class=${specialClassId}` : "Klasse wählen";
  $("radio-url").textContent = specialClassId && control ? `${location.origin}/radio?class=${specialClassId}&control=${control}` : "Klasse und Funkposten wählen";
  const selectedClass = allClasses.find((item) => item.id === specialClassId);
  $("camera-lower-third-url").textContent = selectedClass?.type === "team" && control
    ? `${location.origin}/camera-lower-third?class=${specialClassId}&control=${control}`
    : "Staffelklasse und Funkposten wählen";
}

function setInput(id, prop, value) {
  const el = $(id);
  if (document.activeElement === el) return;
  el[prop] = value;
}

async function refresh() {
  try {
    const [status, disp, classes, controls] = await Promise.all([api("/api/status"), api("/api/display"), api("/api/classes"), api("/api/radio-controls")]);
    config = disp.config;
    allClasses = classes;
    availableControls = controls;

    const m = status.meos;
    const fresh = m.connected && (m.age ?? 999) < 15;
    $("conn").innerHTML = fresh
      ? `<span class="ok">verbunden</span> (vor ${m.age}s aktualisiert)`
      : `<span class="bad">keine aktuellen Daten</span>`;
    $("conn").title = m.url;
    const c = status.competition;
    $("cmp").textContent = c.name
      ? `${c.name} · ${c.date} · Nullzeit ${c.zerotime} · ${status.counts.competitors} Läufer, ${status.counts.teams} Teams`
      : `Quelle: ${m.url}`;
    $("err").textContent = m.last_error ? `Letzter Fehler: ${m.last_error}` : "";

    const cur = disp.current.view;
    const mode = config.mode === "fixed" ? "fixiert" : "Rotation";
    $("now").textContent = cur.class_name
      ? `${cur.class_name} (Seite ${cur.page}/${cur.pages}) – ${mode}`
      : `– (${mode})`;
    $("btn-auto").classList.toggle("active", config.mode === "auto");

    setInput("page-seconds", "value", config.page_seconds);
    setInput("ticker-count", "value", config.ticker_count);
    setInput("show-ticker", "checked", config.show_ticker);
    setInput("hide-empty", "checked", config.hide_empty);

    $("classes").innerHTML = classes.map((k) => {
      const inRot = config.rotate_classes.includes(k.id);
      const fixed = config.mode === "fixed" && config.fixed_class === k.id;
      return `<tr>
        <td><input type="checkbox" data-rot="${k.id}" ${inRot ? "checked" : ""}></td>
        <td><b>${esc(k.name)}</b></td>
        <td>${k.type === "team" ? "Staffel/Team" : "Einzel"}</td>
        <td>${k.finished} / ${k.running} / ${k.entries}</td>
        <td><button data-fix="${k.id}" class="${fixed ? "active" : ""}">Anzeigen</button></td>
      </tr>`;
    }).join("");
    await refreshSpecialViews(classes);
  } catch (e) {
    $("conn").innerHTML = `<span class="bad">Python-Server nicht erreichbar</span>`;
  }
}

$("classes").addEventListener("click", (ev) => {
  const fix = ev.target.dataset.fix;
  if (fix) update({ mode: "fixed", fixed_class: Number(fix) });
  const rot = ev.target.dataset.rot;
  if (rot) {
    const id = Number(rot);
    const set = new Set(config.rotate_classes);
    if (ev.target.checked) set.add(id); else set.delete(id);
    update({ rotate_classes: [...set] });
  }
});

$("btn-auto").addEventListener("click", () => update({ mode: "auto" }));
$("btn-skip").addEventListener("click", async () => {
  if (config.mode !== "auto") await api("/api/display", { mode: "auto" });
  await api("/api/display/skip", {});
  refresh();
});
$("page-seconds").addEventListener("change", (e) => update({ page_seconds: Number(e.target.value) }));
$("ticker-count").addEventListener("change", (e) => update({ ticker_count: Number(e.target.value) }));
$("show-ticker").addEventListener("change", (e) => update({ show_ticker: e.target.checked }));
$("hide-empty").addEventListener("change", (e) => update({ hide_empty: e.target.checked }));
$("special-class").addEventListener("change", () => {
  specialClassId = Number($("special-class").value) || null;
  refreshSpecialViews(allClasses);
});
$("special-runner").addEventListener("change", updateSpecialUrls);
$("special-control").addEventListener("change", updateSpecialUrls);
$("podium-limit").addEventListener("change", async () => {
  if (specialClassId) await api("/api/podium/mode", { class_id: specialClassId, top: Number($("podium-limit").value) });
  updateSpecialUrls();
});
$("podium-controls").addEventListener("click", async (ev) => {
  const place = Number(ev.target.dataset.podiumPlace);
  if (place) await podiumAction(place);
  else if (ev.target.id === "podium-reset") await podiumAction(0);
});

async function podiumAction(place) {
  if (!specialClassId) return;
  if (place > Number($("podium-limit").value)) return;
  if (place) await api("/api/podium/reveal", { class_id: specialClassId, place });
  else await api(`/api/podium/reset/${specialClassId}`, {});
  refresh();
}

document.addEventListener("keydown", (ev) => {
  if (ev.repeat || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (["1", "2", "3", "4", "5", "6"].includes(ev.key)) {
    if (Number(ev.key) > Number($("podium-limit").value)) return;
    ev.preventDefault();
    podiumAction(Number(ev.key));
  } else if (ev.key.toLowerCase() === "r") {
    ev.preventDefault();
    podiumAction(0);
  }
});

$("overlay-url").textContent = `${location.origin}/overlay`;
$("news-url").textContent = `${location.origin}/news`;
refresh();
setInterval(refresh, 2000);
