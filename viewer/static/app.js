"use strict";

const PLOT_LAYOUT = {
  paper_bgcolor: "#26262b",
  plot_bgcolor: "#1e1e22",
  font: { color: "#d6d6dc", family: "ui-monospace, monospace", size: 11 },
  margin: { l: 60, r: 20, t: 30, b: 50 },
};

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// Snapshot of what the client is currently showing; dumped to a file by the
// "Dump Debug" button (only present under `liberty_view --dev`).
const debugState = { meta: null, openCells: {}, lastTable: null };

// ---- library meta + cell list ---------------------------------------------
async function loadMeta() {
  const m = await api("/api/meta");
  const nameEl = document.getElementById("lib-name");
  debugState.meta = m;
  nameEl.textContent = m.library_name;
  nameEl.classList.add("clickable");
  nameEl.onclick = () => {
    document
      .querySelectorAll(".node.selected")
      .forEach((n) => n.classList.remove("selected"));
    renderLibrary(m);
  };
  const energy = energyLabel(m.energy_unit_joules);
  // Drop the leading magnitude ("1ps" -> "ps", "1mA" -> "mA").
  const bare = (u) => (u ? u.replace(/^\s*[0-9.eE+-]+\s*/, "") : u);
  const units = [
    bare(m.voltage_unit),
    bare(m.current_unit),
    bare(m.time_unit),
    energy,
    bare(m.leakage_power_unit),
  ]
    .filter(Boolean)
    .join(" / ");
  document.getElementById("lib-units").textContent =
    `${units} · ${m.num_cells} cells`;
}

const _ENERGY_PREFIX = {
  "-3": "mJ", "-6": "uJ", "-9": "nJ",
  "-12": "pJ", "-15": "fJ", "-18": "aJ", "0": "J",
};
function energyLabel(joules) {
  if (!joules) return null;
  const exp = Math.round(Math.log10(joules));
  return _ENERGY_PREFIX[String(exp)] || `${joules} J`;
}

let filterTimer = null;
async function loadCells(filter) {
  const q = filter ? `?filter=${encodeURIComponent(filter)}` : "";
  const data = await api(`/api/cells${q}`);
  document.getElementById("cell-count").textContent =
    `${data.cells.length} / ${data.total} cells`;
  const tree = document.getElementById("tree");
  tree.innerHTML = "";
  for (const name of data.cells) tree.appendChild(cellNode(name));
}

// ---- tree rendering --------------------------------------------------------
function selectRow(li) {
  document.querySelectorAll(".node.selected").forEach((n) => n.classList.remove("selected"));
  li.classList.add("selected");
}

function cellNode(name) {
  const li = document.createElement("li");
  li.className = "node cell";
  const row = document.createElement("div");
  row.className = "row";
  row.innerHTML = `<span class="toggle">▸</span>${name}`;
  const kids = document.createElement("ul");
  kids.className = "tree hidden";
  let cellData = null;
  row.onclick = async () => {
    const open = !kids.classList.toggle("hidden");
    row.querySelector(".toggle").textContent = open ? "▾" : "▸";
    if (open && !cellData) {
      cellData = await api(`/api/cells/${encodeURIComponent(name)}`);
      debugState.openCells[name] = cellData;
      for (const child of cellData.children || []) kids.appendChild(treeNode(child, name));
    }
    if (open && cellData) {
      selectRow(li);
      renderAttrs(cellData);
      showSource(name, { kind: "cell", name });
    }
  };
  li.appendChild(row);
  li.appendChild(kids);
  return li;
}

function treeNode(node, cellName) {
  const li = document.createElement("li");
  li.className = `node ${node.type}`;
  const row = document.createElement("div");
  row.className = "row";
  const hasKids = node.children && node.children.length;
  if (!hasKids) li.classList.add("leaf");
  const tog = hasKids ? "▸" : "";
  let metaStr = "";
  if (node.meta) {
    if (node.meta.direction) metaStr = ` <span class="meta-inline">${node.meta.direction}${node.meta.function ? " = " + node.meta.function : ""}</span>`;
    else if (node.meta.area != null) metaStr = ` <span class="meta-inline">A=${node.meta.area}</span>`;
  }
  row.innerHTML = `<span class="toggle">${tog}</span>${node.label}${metaStr}`;

  if (node.type === "table") {
    row.onclick = () => {
      selectRow(li);
      loadTable(cellName, node.ref);
      showSource(cellName, node.src);
    };
    li.appendChild(row);
    return li;
  }

  if (node.type === "leakage") {
    row.onclick = () => {
      selectRow(li);
      renderLeakage(node.leakage);
      showSource(cellName, node.src);
    };
    li.appendChild(row);
    return li;
  }

  let kids = null;
  let built = false;
  if (hasKids) {
    kids = document.createElement("ul");
    kids.className = "tree hidden";
  }
  row.onclick = () => {
    if (hasKids) {
      const open = !kids.classList.toggle("hidden");
      row.querySelector(".toggle").textContent = open ? "▾" : "▸";
      if (open && !built) {
        built = true;
        for (const child of node.children) kids.appendChild(treeNode(child, cellName));
      }
    }
    // A node carries its own scalar attributes (pin caps, cell area, arc meta,
    // …) — show them in the main view, not just expand.
    if (node.attributes && node.attributes.length) {
      selectRow(li);
      renderAttrs(node);
      showSource(cellName, node.src);
    }
  };
  li.appendChild(row);
  if (kids) li.appendChild(kids);
  return li;
}

function renderAttrs(node) {
  const view = document.getElementById("view");
  view.innerHTML = "";
  hideWave();
  document.getElementById("crumb").textContent = `${node.label} — attributes`;
  const attrs = node.attributes || [];
  if (!attrs.length) {
    view.innerHTML = '<div class="muted">no scalar attributes</div>';
    return;
  }
  const t = document.createElement("table");
  t.className = "attrs";
  t.innerHTML =
    "<tr><th>attribute</th><th>value</th></tr>" +
    attrs.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("");
  view.appendChild(t);
}

// leakage_power: a when-condition × power-rail table of static leakage values.
function renderLeakage(d) {
  const view = document.getElementById("view");
  view.innerHTML = "";
  hideWave();
  document.getElementById("crumb").textContent = "leakage_power · when × power";
  const cols = d.pg_pins;
  const t = document.createElement("table");
  t.className = "attrs";
  t.innerHTML =
    "<tr><th>when</th>" +
    cols.map((c) => `<th>${c}</th>`).join("") +
    "</tr>" +
    d.rows
      .map(
        (r) =>
          `<tr><th>${r.when}</th>` +
          cols
            .map((c) => `<td class="num">${r.values[c] ?? ""}</td>`)
            .join("") +
          "</tr>"
      )
      .join("");
  view.appendChild(t);
}

// ---- library-level view ----------------------------------------------------
function renderLibrary(m) {
  renderAttrs({ label: m.library_name, attributes: m.attributes });
  const waves = m.driver_waveforms || [];
  if (!waves.length) return;
  const view = document.getElementById("view");

  const h = document.createElement("h3");
  h.className = "section";
  h.textContent = "normalized_driver_waveform — click a waveform to plot it";
  view.appendChild(h);

  const bar = document.createElement("div");
  bar.className = "dw-buttons";
  view.appendChild(bar);

  // Build the detail (caption + table + plot) once and reuse it, so clicking a
  // different waveform updates content in place instead of tearing the subtree
  // down and rebuilding it — that collapse/regrow is what jumped scroll to top.
  const cap = document.createElement("h3");
  cap.className = "section";
  const scroll = document.createElement("div");
  scroll.className = "dw-table-scroll";
  const tbl = document.createElement("table");
  tbl.className = "grid";
  scroll.appendChild(tbl);
  const plotTitle = document.createElement("h3");
  plotTitle.className = "section";
  plotTitle.textContent = "waveform (one curve per slew)";
  const plot = document.createElement("div");
  const refs = { cap, tbl, plot };
  view.append(cap, scroll, plotTitle, plot);

  waves.forEach((w) => {
    const btn = document.createElement("button");
    btn.className = "dw-btn";
    btn.textContent = w.name;
    btn.onclick = () => {
      bar.querySelectorAll(".dw-btn.active").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      updateDriverWaveform(w, refs);
    };
    bar.appendChild(btn);
  });
}

// A normalized_driver_waveform is a 2-D table (slew x normalized voltage -> time).
// Show the raw table, then plot one voltage-vs-time curve per input slew. Updates
// the persistent refs in place (Plotly.react keeps the same div -> no scroll jump).
function updateDriverWaveform(w, refs) {
  const L = w.labels;
  refs.cap.textContent = `${w.name}: ${L.time} for each (${L.slew}, ${L.voltage})`;

  refs.tbl.innerHTML =
    `<tr><th>${L.slew} \\ ${L.voltage}</th>` +
    w.voltage.map((v) => `<th>${v}</th>`).join("") +
    "</tr>" +
    w.slew
      .map(
        (s, i) =>
          `<tr><th>${s}</th>` +
          w.time[i].map((t) => `<td class="num">${t}</td>`).join("") +
          "</tr>"
      )
      .join("");

  const traces = w.slew.map((s, i) => ({
    x: w.time[i],
    y: w.voltage,
    mode: "lines+markers",
    name: `${L.slew}=${s}`,
  }));
  Plotly.react(refs.plot, traces, {
    ...PLOT_LAYOUT,
    xaxis: { title: L.time },
    yaxis: { title: L.voltage, range: [0, 1] },
    legend: { font: { size: 10 } },
  }, { responsive: true });
}

// ---- leaf table rendering --------------------------------------------------
async function loadTable(cell, ref) {
  const params = new URLSearchParams({
    cell,
    pin: ref.pin,
    group: ref.group,
    arc_index: ref.arc_index,
    table: ref.table,
    container: ref.container || "",
  });
  document.getElementById("crumb").textContent =
    `${cell} · ${ref.container ? ref.container + " · " : ""}${ref.pin} · ${ref.group} · ${ref.table}`;
  try {
    const data = await api(`/api/table?${params}`);
    debugState.lastTable = { cell, ref, data };
    renderTable(data, ref);
  } catch (e) {
    document.getElementById("view").innerHTML =
      `<div class="muted">table error: ${e.message}</div>`;
  }
}

function renderTable(data, ref) {
  const view = document.getElementById("view");
  view.innerHTML = "";
  hideWave();
  if (data.kind === "ccs") return renderCcsGrid(view, data);
  if (data.ndim === 0) return renderScalar(view, data);
  if (data.ndim === 1) return renderLine(view, data, ref);
  if (data.ndim === 2) return renderHeatmap(view, data, ref);
  return renderGrid(view, data, ref);
}

// CCS: clickable (slew x cap) grid; each cell holds a current-vs-time wave.
// Grid label = t95 (time current decays to 95% of peak). Click -> wave plot.
function renderCcsGrid(view, data) {
  const L = data.labels || { index_1: "slew", index_2: "cap", time: "time", current: "current" };
  const note = document.createElement("h3");
  note.className = "section";
  note.textContent =
    `${data.table}: ${L.index_1} × ${L.index_2} — cell = time of peak |${L.current}| (${L.time}); click to plot the current wave`;
  view.appendChild(note);

  const tbl = document.createElement("table");
  tbl.className = "grid";
  const head = document.createElement("tr");
  head.innerHTML = `<th>${L.index_1} \\ ${L.index_2}</th>` + data.index_2.map((c) => `<th>${c}</th>`).join("");
  tbl.appendChild(head);

  data.index_1.forEach((slew, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th>${slew}</th>`;
    data.index_2.forEach((cap, j) => {
      const td = document.createElement("td");
      const cellData = data.grid[i][j];
      if (cellData) {
        const btn = document.createElement("button");
        btn.textContent = cellData.t_peak != null ? cellData.t_peak.toPrecision(4) : "·";
        btn.title = `slew=${slew}, cap=${cap}, ref_time=${cellData.reference_time}`;
        btn.onclick = () => {
          tbl.querySelectorAll("button.active").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          showCcsWave(data.table, slew, cap, cellData, data.labels);
        };
        td.appendChild(btn);
      }
      tr.appendChild(td);
    });
    tbl.appendChild(tr);
  });
  view.appendChild(tbl);
}

// CCS/CCSP waves carry a long settling tail (current ~0 out to ~1 ns); without
// clamping, the x-autoscale squishes the real edge into a sliver that reads as
// "nothing". Return the time at which the signal has decayed to <1% of peak.
function activeXMax(time, current) {
  const full = time.length ? time[time.length - 1] : 1;
  let peak = 0;
  for (const v of current) {
    const a = Math.abs(v);
    if (a > peak) peak = a;
  }
  if (peak <= 0) return full;
  const thr = peak * 0.01;
  let last = 0;
  for (let k = 0; k < current.length; k++) {
    if (Math.abs(current[k]) > thr) last = k;
  }
  const x = (time[last] || full) * 1.15;
  return x > 0 ? Math.min(x, full) : full;
}

function showCcsWave(table, slew, cap, cell, L) {
  L = L || { time: "time", current: "current" };
  document.getElementById("wave-section").classList.remove("hidden");
  document.getElementById("wave-title").textContent =
    `${table} · slew=${slew} · cap=${cap} · ref_time=${cell.reference_time} · t_peak=${cell.t_peak != null ? cell.t_peak.toPrecision(4) : "n/a"}`;
  const traces = [{ x: cell.time, y: cell.current, mode: "lines+markers", line: { color: "#7bd88f" }, name: "current" }];
  const shapes = [];
  if (cell.t_peak != null) {
    shapes.push({ type: "line", x0: cell.t_peak, x1: cell.t_peak, yref: "paper", y0: 0, y1: 1, line: { color: "#e6c07b", dash: "dot", width: 1 } });
  }
  Plotly.newPlot("wave", traces, {
    ...PLOT_LAYOUT,
    // Default view to the active region; double-click autoscales to the full tail.
    xaxis: { title: L.time, range: [0, activeXMax(cell.time, cell.current)] },
    yaxis: { title: L.current },
    shapes,
  }, { responsive: true });
}

function labels(data) {
  return data.labels || { index_1: "index_1", index_2: "index_2", index_3: "index_3", value: "value" };
}

function renderScalar(view, data) {
  const L = labels(data);
  const t = document.createElement("table");
  t.className = "scalar";
  t.innerHTML = `<tr><th>${L.value}</th><td>${data.scalar}</td></tr>`;
  view.appendChild(t);
}

function renderLine(view, data, ref) {
  const L = labels(data);
  const div = document.createElement("div");
  view.appendChild(div);
  Plotly.newPlot(div, [{ x: data.index_1, y: data.values, mode: "lines+markers", line: { color: "#5aa9e6" } }], {
    ...PLOT_LAYOUT,
    title: L.value,
    xaxis: { title: L.index_1 },
    yaxis: { title: L.value },
  }, { responsive: true });
}

function renderHeatmap(view, data, ref) {
  const L = labels(data);
  const hover = `${L.index_1}=%{y}<br>${L.index_2}=%{x}<br>${L.value}=%{z}<extra></extra>`;
  const heat = document.createElement("div");
  view.appendChild(heat);
  Plotly.newPlot(heat, [{
    z: data.values, x: data.index_2, y: data.index_1,
    type: "heatmap", colorscale: "Viridis", hovertemplate: hover,
  }], {
    ...PLOT_LAYOUT,
    title: L.value,
    xaxis: { title: L.index_2 },
    yaxis: { title: L.index_1 },
  }, { responsive: true });

  const surfTitle = document.createElement("h3");
  surfTitle.className = "section";
  surfTitle.textContent = "3D surface";
  view.appendChild(surfTitle);
  const surf = document.createElement("div");
  view.appendChild(surf);
  const zmax = Math.max(...data.values.flat());
  Plotly.newPlot(surf, [{
    z: data.values, x: data.index_2, y: data.index_1,
    type: "surface", colorscale: "Viridis", showscale: false, hovertemplate: hover,
  }], {
    ...PLOT_LAYOUT,
    height: 460,
    scene: {
      // Equal x/y screen extent, z capped at 50% of it, so steep z ranges
      // don't render as a cliff regardless of the data's value range.
      aspectmode: "manual",
      aspectratio: { x: 1, y: 1, z: 0.5 },
      xaxis: { title: L.index_2 },
      yaxis: { title: L.index_1 },
      zaxis: { title: L.value, range: [0, zmax] },
    },
  }, { responsive: true });
}

// 3D table -> clickable (index_1 x index_2) grid; cell click -> wave over index_3.
function renderGrid(view, data, ref) {
  const L = labels(data);
  const note = document.createElement("h3");
  note.className = "section";
  note.textContent = `${data.table}: ${L.index_1} × ${L.index_2} grid — click a cell to plot the ${L.index_3} wave`;
  view.appendChild(note);

  const tbl = document.createElement("table");
  tbl.className = "grid";
  const head = document.createElement("tr");
  head.innerHTML = `<th></th>` + data.index_2.map((v) => `<th>${v}</th>`).join("");
  tbl.appendChild(head);

  data.index_1.forEach((y, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<th>${y}</th>`;
    data.index_2.forEach((x, j) => {
      const td = document.createElement("td");
      const wave = data.values[i][j];
      const summary = Math.max(...wave.map(Math.abs)).toPrecision(3);
      const btn = document.createElement("button");
      btn.textContent = summary;
      btn.title = `index_1=${y}, index_2=${x}`;
      btn.onclick = () => {
        tbl.querySelectorAll("button.active").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        showWave(data, i, j);
      };
      td.appendChild(btn);
      tr.appendChild(td);
    });
    tbl.appendChild(tr);
  });
  view.appendChild(tbl);
}

function showWave(data, i, j) {
  const L = labels(data);
  document.getElementById("wave-section").classList.remove("hidden");
  document.getElementById("wave-title").textContent =
    `${data.table} wave @ ${L.index_1}=${data.index_1[i]}, ${L.index_2}=${data.index_2[j]}`;
  Plotly.newPlot("wave", [{
    x: data.index_3, y: data.values[i][j], mode: "lines", line: { color: "#7bd88f" },
  }], {
    ...PLOT_LAYOUT,
    xaxis: { title: L.index_3 },
    yaxis: { title: L.value },
  }, { responsive: true });
}

function hideWave() {
  document.getElementById("wave-section").classList.add("hidden");
}

// ---- raw cell source (bottom pane) -----------------------------------------
// One byte-slice per cell from the server's in-memory buffer (cached per cell, so
// re-selecting never refetches — cost is O(cell size), snappy on multi-GB libs).
// The view is then scoped to the selected node's group (cell/pin/bus/bundle) by
// brace-matching that group out of the cached cell text, here in the browser.
const _sourceCache = {};

function _escRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Return the index of the `}` matching the `{` at `open`, ignoring braces inside
// quoted strings and #/// /* */ comments.
function _matchBrace(text, open) {
  let depth = 0;
  let line = false;
  let block = false;
  let str = false;
  for (let i = open; i < text.length; i++) {
    const c = text[i];
    const n = text[i + 1];
    if (line) { if (c === "\n") line = false; continue; }
    if (block) { if (c === "*" && n === "/") { block = false; i++; } continue; }
    if (str) { if (c === "\\") i++; else if (c === '"') str = false; continue; }
    if (c === '"') { str = true; continue; }
    if (c === "#") { line = true; continue; }
    if (c === "/" && n === "/") { line = true; i++; continue; }
    if (c === "/" && n === "*") { block = true; i++; continue; }
    if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) return i; }
  }
  return -1;
}

// Slice the `kind (name) { ... }` group (including its header line) out of text.
function _sliceGroup(text, kind, name) {
  const hdr = new RegExp(
    `(?:^|\\n)([ \\t]*)${_escRe(kind)}[ \\t]*\\([ \\t]*${_escRe(name)}[ \\t]*\\)[ \\t]*\\{`
  );
  const m = hdr.exec(text);
  if (!m) return null;
  const start = m.index + (text[m.index] === "\n" ? 1 : 0);
  const end = _matchBrace(text, text.indexOf("{", m.index));
  return end < 0 ? null : text.slice(start, end + 1);
}

async function showSource(cell, src) {
  src = src || { kind: "cell", name: cell };
  const sec = document.getElementById("source-section");
  const title = document.getElementById("source-title");
  const pre = document.getElementById("source");
  sec.classList.remove("hidden");
  if (_sourceCache[cell] === undefined) {
    try {
      _sourceCache[cell] = await api(`/api/cells/${encodeURIComponent(cell)}/source`);
    } catch (e) {
      title.textContent = `source: ${cell} — error: ${e.message}`;
      pre.textContent = "";
      return;
    }
  }
  const d = _sourceCache[cell];
  let text = d.text;
  let label = `${cell} · cell`;
  if (src.kind !== "cell") {
    const slice = _sliceGroup(d.text, src.kind, src.name);
    if (slice !== null) {
      text = slice;
      label = `${src.name} · ${src.kind}`;
    }
  }
  const lines = text.split("\n").length;
  const trunc = src.kind === "cell" && d.truncated ? ", truncated" : "";
  title.textContent = `source: ${label} (${lines.toLocaleString()} lines${trunc})`;
  pre.textContent = text;
}

// ---- debug dump (only when the server runs with --dev) ---------------------
async function dumpDebug() {
  const status = document.getElementById("dump-status");
  const payload = {
    timestamp: new Date().toISOString(),
    url: location.href,
    crumb: document.getElementById("crumb").textContent,
    selected:
      document.querySelector(".node.selected > .row")?.textContent?.trim() || null,
    meta: debugState.meta,
    openCells: debugState.openCells,
    lastTable: debugState.lastTable,
  };
  try {
    const res = await fetch("/api/debug", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    const out = await res.json();
    status.textContent = `wrote ${out.path}`;
  } catch (e) {
    status.textContent = `dump failed: ${e.message}`;
  }
}

// Re-exec the server, wait for it to come back, then reload the page — picks up
// rebuilt native code / edited Python without a manual restart.
async function devRestart() {
  const status = document.getElementById("dump-status");
  status.textContent = "restarting…";
  try {
    await fetch("/api/restart", { method: "POST" });
  } catch {
    /* connection drops as the process re-execs — expected */
  }
  for (let i = 0; i < 100; i++) {
    await new Promise((r) => setTimeout(r, 300));
    try {
      const res = await fetch("/api/config", { cache: "no-store" });
      if (res.ok) {
        location.reload();
        return;
      }
    } catch {
      /* not back yet */
    }
  }
  status.textContent = "restart: server did not come back";
}

async function initDevBar() {
  try {
    const cfg = await api("/api/config");
    if (!cfg.dev) return;
    document.getElementById("devbar").classList.remove("hidden");
    document.getElementById("dump-debug").addEventListener("click", dumpDebug);
    document.getElementById("dev-reload").addEventListener("click", devRestart);
  } catch (e) {
    console.error(e);
  }
}

// ---- boot ------------------------------------------------------------------
document.getElementById("filter").addEventListener("input", (e) => {
  clearTimeout(filterTimer);
  const v = e.target.value;
  filterTimer = setTimeout(() => loadCells(v), 200);
});

loadMeta().catch((e) => (document.getElementById("lib-name").textContent = "error: " + e.message));
loadCells("").catch((e) => console.error(e));
initDevBar();

// Let the server exit when this tab goes away: heartbeat while open, beacon on
// close. A refresh fires the beacon too, but the reloaded page re-pings inside
// the server's grace window, so it survives. (Disabled by --no-exit-on-close.)
function heartbeat() {
  fetch("/api/ping").catch(() => {});
}
heartbeat();
setInterval(heartbeat, 5000);
addEventListener("pageshow", heartbeat);
addEventListener("pagehide", () => navigator.sendBeacon("/api/bye"));
