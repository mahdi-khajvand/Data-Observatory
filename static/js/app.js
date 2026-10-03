const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const API = "";

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (err ? " err" : "");
  setTimeout(() => t.classList.remove("show"), 3200);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const res = await fetch(API + path, { ...opts, headers });
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error((data && (data.detail || data.error)) || res.statusText);
  return data;
}

function badge(status) {
  const s = String(status || "").toLowerCase();
  let cls = "info";
  if (["healthy", "pass", "online", "success"].includes(s)) cls = "healthy";
  else if (["warning", "warn", "degraded"].includes(s)) cls = "warning";
  else if (["critical", "fail", "failed"].includes(s)) cls = "critical";
  const label = status || "—";
  return `<span class="badge ${cls}">${label}</span>`;
}

function fmtNum(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US");
}

/** Safe Plotly wrapper — works offline with local plotly.min.js */
function safePlot(id, data, layout, config) {
  const el = document.getElementById(id);
  if (!el) return;
  if (typeof Plotly === "undefined") {
    el.innerHTML = '<div class="muted" style="padding:24px;text-align:center">Plotly offline — نمودار در دسترس نیست. فایل plotly.min.js را بررسی کنید.</div>';
    return;
  }
  const cfg = Object.assign({ displayModeBar: false, responsive: true }, config || {});
  Plotly.newPlot(id, data, layout, cfg);
}

const TITLES = {
  overview: ["PLATFORM", "Overview"],
  catalog: ["ASSETS", "Data Catalog"],
  freshness: ["MONITORING", "Data Freshness"],
  metadata: ["CATALOG", "Metadata Studio"],
  quality: ["QUALITY", "Data Quality"],
  profiler: ["ANALYTICS", "Data Profiler"],
  bi: ["BUSINESS INTELLIGENCE", "BI Studio"],
  sql: ["EXPLORER", "SQL Explorer"],
  growth: ["TRENDS", "Table Growth"],
  alerts: ["OPS", "Alert Center"],
  discover: ["INGEST", "Auto Discovery"],
  assistant: ["AI", "رصدیار · دستیار هوشمند"],
  ml: ["ML", "Machine Learning Studio"],
  pipeline: ["DATA PLATFORM", "Pipeline Studio"],
};

function showPage(name) {
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  const [eye, title] = TITLES[name] || ["PAGE", name];
  $("#pageEyebrow").textContent = eye;
  $("#pageTitle").textContent = title;
  const map = {
    overview: loadOverview,
    catalog: loadCatalog,
    freshness: loadFreshness,
    metadata: loadMetadata,
    quality: loadQuality,
    profiler: loadProfiler,
    bi: loadBi,
    sql: loadSql,
    growth: loadGrowth,
    alerts: loadAlerts,
    discover: loadDiscover,
    assistant: loadAssistant,
    ml: loadML,
    pipeline: loadPipeline,
  };
  if (map[name]) map[name]();
}

/* ---------- Overview ---------- */
async function loadOverview() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">Loading dashboard…</div>`;
  try {
    const s = await api("/api/overview");
    $("#sideHealth").textContent = `Health ${s.health_score}/100`;
    $("#sideScan").textContent = s.last_scan
      ? `Last scan: ${s.last_scan.finished_at || "—"}`
      : "No scan yet";

    const pct = Math.max(0, Math.min(100, s.health_score));
    el.innerHTML = `
      <div class="health-hero">
        <div class="score-circle" style="--pct:${pct}">
          <span>${s.health_score}</span>
        </div>
        <div style="flex:1">
          <div class="eyebrow">DATA HEALTH SCORE</div>
          <h3 style="margin:6px 0 8px;font-size:1.35rem">Enterprise Data Health</h3>
          <div class="bar" style="max-width:420px;height:12px"><i style="width:${pct}%"></i></div>
          <p class="muted" style="margin:10px 0 0;font-size:.88rem">
            ${s.status_breakdown.healthy} healthy · ${s.status_breakdown.warning} warning · ${s.status_breakdown.critical} critical
            · ${s.open_alerts} open alerts
          </p>
        </div>
        <div class="row-actions">
          ${s.db_list.map((d) => `<span class="stat-chip"><b>${d.type}</b> ${d.name} ${badge(d.status)}</span>`).join("")}
        </div>
      </div>

      <div class="grid-kpi">
        <div class="kpi"><div class="label">Databases</div><div class="value">${s.databases}</div><div class="sub">connected sources</div></div>
        <div class="kpi cyan"><div class="label">Tables</div><div class="value">${fmtNum(s.tables)}</div><div class="sub">in catalog</div></div>
        <div class="kpi green"><div class="label">Records</div><div class="value">${s.records_human}</div><div class="sub">${s.size_human} total size</div></div>
        <div class="kpi amber"><div class="label">Data Freshness</div><div class="value">${s.data_freshness_pct}%</div><div class="sub">tables on SLA</div></div>
      </div>

      <div class="grid-kpi">
        <div class="kpi amber"><div class="label">⚠️ Stale Tables</div><div class="value">${s.stale_tables}</div><div class="sub">need attention</div></div>
        <div class="kpi red"><div class="label">🔴 Failed Checks</div><div class="value">${s.failed_checks}</div><div class="sub">quality failures</div></div>
        <div class="kpi pink"><div class="label">📈 Data Growth</div><div class="value">+${s.growth_pct}%</div><div class="sub">avg weekly</div></div>
        <div class="kpi cyan"><div class="label">🔄 Last Scan</div><div class="value" style="font-size:1.1rem">${s.last_scan ? (s.last_scan.finished_at || "").slice(11, 16) : "—"}</div><div class="sub">${s.last_scan ? s.last_scan.tables_scanned + " tables" : "never"}</div></div>
      </div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-head"><h3>🔥 Problematic Tables</h3></div>
          <div class="table-wrap"><table>
            <thead><tr><th>Database</th><th>Table</th><th>Status</th><th>Last Update</th><th>Rows</th><th>Issue</th></tr></thead>
            <tbody>
              ${s.problematic.map((p) => `
                <tr style="cursor:pointer" data-tid="${p.table_id}">
                  <td>${p.database}</td>
                  <td class="mono">${p.table}</td>
                  <td>${badge(p.status)}</td>
                  <td>${p.last_update || "—"}</td>
                  <td>${p.rows_human}</td>
                  <td>${p.issue}</td>
                </tr>`).join("") || `<tr><td colspan="6" class="muted">All tables healthy 🎉</td></tr>`}
            </tbody>
          </table></div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>Status Distribution</h3></div>
          <div id="chartStatus" class="chart"></div>
        </div>
      </div>
    `;

    safePlot("chartStatus", [{
      type: "pie",
      labels: ["Healthy", "Warning", "Critical"],
      values: [s.status_breakdown.healthy, s.status_breakdown.warning, s.status_breakdown.critical],
      marker: { colors: ["#22c55e", "#f59e0b", "#ef4444"] },
      hole: .55,
      textinfo: "label+value",
    }], {
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { color: "#94a3b8", size: 12 },
      margin: { t: 20, b: 20, l: 20, r: 20 },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });

    el.querySelectorAll("[data-tid]").forEach((tr) => {
      tr.onclick = () => openTable(Number(tr.dataset.tid));
    });
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

/* ---------- Catalog ---------- */
let _catalogTree = null;
let _catalogSelectedDb = null;
let _compareIds = [];

async function loadCatalog() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">Loading catalog…</div>`;
  try {
    _catalogTree = await api("/api/catalog");
    _catalogSelectedDb = null;
    _compareIds = [];
    renderCatalog();
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

function renderCatalog() {
  const el = $("#content");
  const tree = _catalogTree || [];
  const totalTables = tree.reduce((n, db) => n + db.schemas.reduce((m, s) => m + s.tables.length, 0), 0);
  el.innerHTML = `
    <div class="catalog-layout">
      <div class="catalog-dbs">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <strong style="font-size:.9rem">Databases</strong>
          <span class="muted" style="font-size:.75rem">${tree.length} DB · ${totalTables} table</span>
        </div>
        <input id="dbSearch" placeholder="جستجوی دیتابیس…" style="width:100%;margin-bottom:10px;padding:7px 10px;font-size:.85rem" />
        <div id="dbList">
          ${tree.map((db) => `
            <div class="catalog-db-item ${ _catalogSelectedDb === db.id ? "active" : "" }" data-dbid="${db.id}">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <strong>${db.name}</strong>
                ${badge(db.status)}
              </div>
              <div class="db-meta">${db.type} · ${db.host} · ${db.schemas.reduce((n,s)=>n+s.tables.length,0)} tables</div>
            </div>
          `).join("")}
        </div>
      </div>
      <div class="catalog-main">
        <div id="catalogTablesArea">
          <div class="panel">
            <p class="muted" style="margin:0">یک دیتابیس از سمت راست انتخاب کنید تا لیست جداول نمایش داده شود.</p>
          </div>
        </div>
        <div id="tableDetail" style="margin-top:16px"></div>
      </div>
    </div>
  `;
  $("#dbSearch").oninput = (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$("#dbList .catalog-db-item").forEach((item) => {
      const name = item.querySelector("strong").textContent.toLowerCase();
      item.style.display = !q || name.includes(q) ? "" : "none";
    });
  };
  $$("#dbList .catalog-db-item").forEach((item) => {
    item.onclick = () => {
      _catalogSelectedDb = Number(item.dataset.dbid);
      _compareIds = [];
      renderCatalogTables();
      $$("#dbList .catalog-db-item").forEach((x) => x.classList.toggle("active", Number(x.dataset.dbid) === _catalogSelectedDb));
    };
  });
  if (_catalogSelectedDb) renderCatalogTables();
}

function renderCatalogTables() {
  const area = $("#catalogTablesArea");
  if (!area || !_catalogTree) return;
  const db = _catalogTree.find((d) => d.id === _catalogSelectedDb);
  if (!db) {
    area.innerHTML = `<div class="panel"><p class="muted">دیتابیس یافت نشد.</p></div>`;
    return;
  }
  const allTables = [];
  db.schemas.forEach((sc) => {
    sc.tables.forEach((t) => allTables.push({ ...t, schema: sc.name }));
  });
  area.innerHTML = `
    <div class="panel" style="margin-bottom:12px">
      <div class="panel-head">
        <div>
          <div class="eyebrow">${db.type} · ${db.host}</div>
          <h3 style="margin:4px 0 0">${db.name}</h3>
        </div>
        <span class="muted">${allTables.length} tables · ${db.schemas.length} schemas</span>
      </div>
      <div class="catalog-compare-bar">
        <span class="muted" style="font-size:.85rem">مقایسه جداول:</span>
        <span id="compareChips" class="muted" style="font-size:.85rem">حداکثر ۲ جدول انتخاب کنید (کلیک روی کارت)</span>
        <button class="btn btn-sm" id="btnClearCompare" style="margin-right:auto">پاک کردن انتخاب</button>
        <button class="btn primary btn-sm" id="btnDoCompare" disabled>مقایسه کنار هم</button>
      </div>
      <input id="tblSearch" placeholder="جستجوی جدول…" style="width:100%;margin-bottom:12px;padding:8px 10px" />
      <div class="catalog-tables-grid" id="tblGrid">
        ${allTables.map((t) => `
          <div class="catalog-table-card ${_compareIds.includes(t.id) ? "selected" : ""}" data-tid="${t.id}">
            <div style="display:flex;justify-content:space-between;align-items:start;gap:8px">
              <div>
                <div class="tname">${t.name}</div>
                <div class="muted" style="font-size:.72rem;margin-top:2px">📂 ${t.schema}</div>
              </div>
              ${badge(t.status)}
            </div>
            <div class="muted" style="font-size:.78rem;margin-top:8px">${t.rows_human} · ${t.size_human}</div>
          </div>
        `).join("") || `<p class="muted">جدولی نیست</p>`}
      </div>
    </div>
  `;
  const updateCompareUI = () => {
    const chips = $("#compareChips");
    if (_compareIds.length === 0) chips.textContent = "حداکثر ۲ جدول انتخاب کنید (کلیک روی کارت)";
    else {
      const names = _compareIds.map((id) => {
        const t = allTables.find((x) => x.id === id);
        return t ? t.name : id;
      });
      chips.innerHTML = names.map((n) => `<span class="stat-chip"><b>${n}</b></span>`).join(" ");
    }
    $("#btnDoCompare").disabled = _compareIds.length !== 2;
    $$("#tblGrid .catalog-table-card").forEach((c) => {
      c.classList.toggle("selected", _compareIds.includes(Number(c.dataset.tid)));
    });
  };
  $$("#tblGrid .catalog-table-card").forEach((card) => {
    card.onclick = (ev) => {
      const id = Number(card.dataset.tid);
      // shift or long: compare toggle; normal click: open detail
      if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
        if (_compareIds.includes(id)) _compareIds = _compareIds.filter((x) => x !== id);
        else if (_compareIds.length < 2) _compareIds.push(id);
        else { _compareIds = [_compareIds[1], id]; }
        updateCompareUI();
      } else {
        openTable(id);
      }
    };
  });
  $("#btnClearCompare").onclick = () => { _compareIds = []; updateCompareUI(); $("#tableDetail").innerHTML = ""; };
  $("#btnDoCompare").onclick = () => {
    if (_compareIds.length === 2) openTableCompare(_compareIds[0], _compareIds[1]);
  };
  $("#tblSearch").oninput = (e) => {
    const q = e.target.value.trim().toLowerCase();
    $$("#tblGrid .catalog-table-card").forEach((c) => {
      const name = c.querySelector(".tname").textContent.toLowerCase();
      c.style.display = !q || name.includes(q) ? "" : "none";
    });
  };
  updateCompareUI();
}

async function openTable(id) {
  const box = $("#tableDetail") || $("#content");
  try {
    const t = await api(`/api/tables/${id}`);
    const html = renderTableDetailPanel(t);
    if ($("#tableDetail")) $("#tableDetail").innerHTML = html;
    else {
      showPage("catalog");
      setTimeout(async () => {
        await loadCatalog();
        if ($("#tableDetail")) $("#tableDetail").innerHTML = html;
      }, 100);
    }
  } catch (e) {
    toast(e.message, true);
  }
}

function renderTableDetailPanel(t) {
  return `
    <div class="panel" style="border-color:rgba(6,182,212,.3)">
      <div class="panel-head">
        <div>
          <div class="eyebrow">${t.database} / ${t.schema}</div>
          <h3 style="margin:4px 0 0;font-size:1.25rem">${t.table_name}</h3>
        </div>
        ${badge(t.status)}
      </div>
      <div class="grid-kpi" style="margin-top:8px">
        <div class="kpi"><div class="label">Rows</div><div class="value" style="font-size:1.3rem">${t.rows_human}</div></div>
        <div class="kpi cyan"><div class="label">Size</div><div class="value" style="font-size:1.3rem">${t.size_human}</div></div>
        <div class="kpi green"><div class="label">Columns</div><div class="value" style="font-size:1.3rem">${t.columns.length}</div></div>
        <div class="kpi amber"><div class="label">Last Update</div><div class="value" style="font-size:.95rem">${t.last_update || "—"}</div>
          <div class="sub">delay ${t.delay_hours}h · SLA ${t.sla_hours}h</div></div>
      </div>
      ${t.health ? `
      <div class="stat-chip">Overall <b>${t.health.overall}</b></div>
      <div class="stat-chip">Freshness <b>${t.health.freshness}</b></div>
      <div class="stat-chip">Completeness <b>${t.health.completeness}</b></div>
      <div class="stat-chip">Duplicates <b>${t.health.duplicates}</b></div>
      <div class="stat-chip">Validity <b>${t.health.validity}</b></div>
      ` : ""}
      <h3 style="margin-top:18px">Columns</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Column</th><th>Type</th><th>Nullable</th><th>Null %</th><th>Distinct</th><th>Example</th></tr></thead>
        <tbody>
          ${t.columns.map((c) => `
            <tr>
              <td class="mono">${c.column_name}</td>
              <td>${c.data_type}</td>
              <td>${c.nullable ? "Yes" : "No"}</td>
              <td>${c.null_pct}%</td>
              <td>${c.distinct_pct}%</td>
              <td class="mono">${c.example_value || "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table></div>
      ${t.schema_history?.length ? `
        <h3 style="margin-top:18px">Schema History</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>Time</th><th>Type</th><th>Detail</th></tr></thead>
          <tbody>
            ${t.schema_history.map((h) => `
              <tr><td>${h.change_time}</td><td>${badge(h.change_type === "ADD_COLUMN" ? "warning" : "info")}</td><td class="mono">${h.detail}</td></tr>
            `).join("")}
          </tbody>
        </table></div>` : ""}
    </div>`;
}

async function openTableCompare(id1, id2) {
  const box = $("#tableDetail");
  if (!box) return;
  box.innerHTML = `<div class="empty">Loading comparison…</div>`;
  try {
    const [t1, t2] = await Promise.all([api(`/api/tables/${id1}`), api(`/api/tables/${id2}`)]);
    box.innerHTML = `
      <div class="compare-grid">
        ${renderTableDetailPanel(t1)}
        ${renderTableDetailPanel(t2)}
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="panel-head"><h3>🔍 Column Diff</h3></div>
        ${columnDiffHtml(t1, t2)}
      </div>`;
  } catch (e) {
    box.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

function columnDiffHtml(t1, t2) {
  const m1 = Object.fromEntries((t1.columns || []).map((c) => [c.column_name, c]));
  const m2 = Object.fromEntries((t2.columns || []).map((c) => [c.column_name, c]));
  const all = Array.from(new Set([...Object.keys(m1), ...Object.keys(m2)])).sort();
  return `<div class="table-wrap"><table>
    <thead><tr><th>Column</th><th>${t1.table_name}</th><th>${t2.table_name}</th><th>Match</th></tr></thead>
    <tbody>
      ${all.map((name) => {
        const a = m1[name]; const b = m2[name];
        let match = "—";
        if (a && b) match = a.data_type === b.data_type ? badge("healthy") : badge("warning");
        else match = badge("critical");
        return `<tr>
          <td class="mono">${name}</td>
          <td>${a ? a.data_type : "<span class='muted'>—</span>"}</td>
          <td>${b ? b.data_type : "<span class='muted'>—</span>"}</td>
          <td>${match}</td>
        </tr>`;
      }).join("")}
    </tbody>
  </table></div>`;
}

/* ---------- Freshness ---------- */
let _freshFilter = "all";

async function loadFreshness() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">Loading freshness dashboard…</div>`;
  try {
    const dash = await api("/api/freshness/dashboard");
    const k = dash.kpis || {};
    const rows = dash.tables || [];
    el.innerHTML = `
      <div class="fresh-kpi-row">
        <div class="kpi"><div class="label">کل جداول</div><div class="value">${k.total_tables ?? 0}</div></div>
        <div class="kpi green"><div class="label">Healthy</div><div class="value">${k.healthy ?? 0}</div><div class="sub">on expected interval</div></div>
        <div class="kpi amber"><div class="label">Warning</div><div class="value">${k.warning ?? 0}</div><div class="sub">past expected</div></div>
        <div class="kpi red"><div class="label">Critical</div><div class="value">${k.critical ?? 0}</div><div class="sub">SLA breached</div></div>
        <div class="kpi cyan"><div class="label">On SLA %</div><div class="value">${k.on_sla_pct ?? 0}%</div></div>
        <div class="kpi"><div class="label">Avg Delay</div><div class="value" style="font-size:1.2rem">${k.avg_delay_hours ?? 0}h</div></div>
      </div>

      <div class="panel" style="margin-bottom:16px">
        <div class="panel-head">
          <h3>📈 روند تازه‌سازی (۳۰ روز)</h3>
          <span class="muted">${dash.last_scan ? "آخرین اسکن: " + (dash.last_scan.finished_at || "—") : "هنوز اسکنی ثبت نشده"}</span>
        </div>
        <div id="chartFreshTrend" class="chart chart-tall"></div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h3>🔄 Freshness & SLA</h3>
          <button class="btn primary btn-sm" id="btnFreshScan">↻ اسکن روزانه همه جداول</button>
        </div>
        <p class="muted" style="margin-bottom:12px;font-size:.85rem">
          <b>Expected</b> = هر چند ساعت باید داده بیاید ·
          <b>SLA</b> = حداکثر تأخیر مجاز قبل از هشدار Critical ·
          اگر Delay &gt; Expected → Warning · اگر Delay &gt; SLA → Critical + Alert
        </p>
        <div class="fresh-filters" id="freshFilters">
          <button data-f="all" class="active">همه (${rows.length})</button>
          <button data-f="healthy">Healthy (${k.healthy || 0})</button>
          <button data-f="warning">Warning (${k.warning || 0})</button>
          <button data-f="critical">Critical (${k.critical || 0})</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th></th><th>Database</th><th>Table</th>
            <th>Expected (h)</th><th>SLA (h)</th>
            <th>Last Update</th><th>Delay</th><th>Status</th><th></th>
          </tr></thead>
          <tbody id="freshBody">
            ${rows.map((r) => `
              <tr data-tid="${r.table_id}" data-status="${r.status}">
                <td><span class="fresh-status-dot ${r.status}"></span></td>
                <td>${r.database}</td>
                <td class="mono">${r.table}</td>
                <td><input type="number" min="0.5" step="0.5" value="${r.expected_interval_hours}" data-exp="${r.table_id}" style="width:70px;padding:4px 6px" /></td>
                <td><input type="number" min="0.5" step="0.5" value="${r.sla_hours}" data-sla="${r.table_id}" style="width:70px;padding:4px 6px" /></td>
                <td>${r.last_update || "—"}</td>
                <td><b>${r.delay_hours}h</b></td>
                <td>${badge(r.status)}</td>
                <td><button class="btn btn-sm" data-save-sla="${r.table_id}">ذخیره</button></td>
              </tr>`).join("")}
          </tbody>
        </table></div>
      </div>
      <div class="panel"><div id="chartFresh" class="chart"></div></div>
    `;

    // trend chart
    const trend = dash.trend || [];
    if (trend.length) {
      safePlot("chartFreshTrend", [
        {
          type: "scatter", mode: "lines+markers",
          name: "Avg Freshness",
          x: trend.map((t) => t.day),
          y: trend.map((t) => t.avg_freshness),
          line: { color: "#22c55e", width: 3 },
          marker: { size: 6 },
        },
        {
          type: "scatter", mode: "lines+markers",
          name: "Avg Overall Health",
          x: trend.map((t) => t.day),
          y: trend.map((t) => t.avg_overall),
          line: { color: "#8b5cf6", width: 2, dash: "dot" },
          marker: { size: 5 },
        },
      ], {
        paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        font: { color: "#94a3b8" },
        margin: { t: 20, b: 40, l: 50, r: 20 },
        legend: { orientation: "h", y: 1.12 },
        xaxis: { gridcolor: "rgba(148,163,184,.08)" },
        yaxis: { gridcolor: "rgba(148,163,184,.08)", range: [0, 105], title: "Score" },
      });
    } else {
      const te = $("#chartFreshTrend");
      if (te) te.innerHTML = `<p class="muted" style="padding:24px;text-align:center">هنوز داده روندی نیست — یک بار <b>Run Scan</b> یا اسکن روزانه را بزنید.</p>`;
    }

    // delay bar chart
    const top = rows.slice().sort((a, b) => b.delay_hours - a.delay_hours).slice(0, 15);
    safePlot("chartFresh", [{
      type: "bar", orientation: "h",
      y: top.map((r) => r.table).reverse(),
      x: top.map((r) => r.delay_hours).reverse(),
      marker: { color: top.map((r) => r.status === "critical" ? "#ef4444" : r.status === "warning" ? "#f59e0b" : "#22c55e").reverse() },
    }], {
      title: { text: "Top delays (hours)", font: { color: "#94a3b8", size: 13 } },
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { color: "#94a3b8" }, margin: { t: 40, b: 40, l: 140, r: 20 },
      xaxis: { gridcolor: "rgba(148,163,184,.1)" }, yaxis: { gridcolor: "rgba(148,163,184,.05)" },
    });

    // filters
    $$("#freshFilters button").forEach((btn) => {
      btn.onclick = () => {
        _freshFilter = btn.dataset.f;
        $$("#freshFilters button").forEach((b) => b.classList.toggle("active", b.dataset.f === _freshFilter));
        $$("#freshBody tr").forEach((tr) => {
          const st = tr.dataset.status;
          tr.style.display = (_freshFilter === "all" || st === _freshFilter) ? "" : "none";
        });
      };
    });

    $("#btnFreshScan").onclick = async () => {
      try {
        toast("در حال اسکن همه جداول…");
        const res = await api("/api/scan", { method: "POST" });
        toast(`اسکن شد: ${res.tables} جدول · H:${res.status_breakdown?.healthy} W:${res.status_breakdown?.warning} C:${res.status_breakdown?.critical}`);
        loadFreshness();
      } catch (e) { toast(e.message, true); }
    };

    el.querySelectorAll("[data-save-sla]").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.dataset.saveSla;
        const exp = el.querySelector(`[data-exp="${id}"]`).value;
        const sla = el.querySelector(`[data-sla="${id}"]`).value;
        try {
          const res = await api(`/api/tables/${id}/sla`, {
            method: "PUT",
            body: JSON.stringify({ expected_interval_hours: Number(exp), sla_hours: Number(sla) }),
          });
          toast(res.status === "critical" ? "ذخیره شد — وضعیت Critical" : res.status === "warning" ? "ذخیره شد — Warning" : "ذخیره شد ✓");
          loadFreshness();
        } catch (e) { toast(e.message, true); }
      };
    });
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}


/* ---------- Schema ---------- */
async function loadMetadata() {
  const el = $("#content");
  try {
    const tables = await api("/api/metadata/tables");
    el.innerHTML = `
      <div class="grid-2" style="align-items:start">
        <div class="panel">
          <div class="panel-head"><h3>📚 جداول</h3>
            <div class="row-actions">
              <span class="muted">${tables.length} table</span>
              <button class="btn btn-sm" id="btnApplyPacks">📚 Apply Packs</button>
              <button class="btn btn-sm" id="btnAiExport">⬇ Export AI Catalog</button>
            </div>
          </div>
          <input id="metaSearch" placeholder="جستجوی جدول…" style="width:100%;margin-bottom:10px;padding:8px 10px" />
          <div id="metaList" style="max-height:70vh;overflow:auto">
            ${tables.map((t) => `
              <div class="sql-item" data-mid="${t.id}" style="cursor:pointer;padding:8px 10px;border-radius:8px;margin-bottom:4px">
                <div class="mono" style="font-size:.85rem">${t.db_name}.${t.schema_name}.${t.table_name}</div>
                <div class="muted" style="font-size:.75rem">${t.description ? t.description.slice(0,80) : "بدون توضیح"}</div>
              </div>`).join("")}
          </div>
        </div>
        <div class="panel" id="metaEditor">
          <p class="muted">یک جدول انتخاب کنید تا metadata غنی (مناسب AI) را ویرایش کنید.</p>
        </div>
      </div>
    `;

    const esc = (s) => String(s ?? "").replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;");
    const openMeta = async (id) => {
      const d = await api(`/api/tables/${id}`);
      const ed = $("#metaEditor");
      const cols = d.columns || [];
      ed.innerHTML = `
        <div class="panel-head">
          <div>
            <div class="eyebrow">${d.database} / ${d.schema}</div>
            <h3 class="mono" style="margin:4px 0 0">${d.table_name}</h3>
          </div>
          <div class="row-actions">
            <button class="btn primary btn-sm" id="btnAutoMeta">✨ تولید خودکار</button>
            <button class="btn btn-sm" id="btnAiMeta">🤖 AI JSON</button>
          </div>
        </div>
        <div class="field"><span>توضیح جدول</span>
          <textarea id="tblDesc" rows="2" style="width:100%;padding:8px">${esc(d.description)}</textarea>
        </div>
        <div class="grid-2">
          <div class="field"><span>Owner</span><input id="tblOwner" value="${esc(d.owner)}" /></div>
          <div class="field"><span>Tags</span><input id="tblTags" value="${esc(d.tags)}" placeholder="finance, daily, pii" /></div>
        </div>
        <button class="btn primary" id="btnSaveTbl">ذخیره جدول</button>

        <h4 style="margin-top:22px">ستون‌ها · متادیتا برای AI</h4>
        <p class="muted" style="font-size:.8rem;margin:4px 0 12px">
          هر ستون را باز کنید و business_name، semantic_type، unit، synonyms و … را پر کنید.
          این ساختار برای RAG و Agent بهینه است.
        </p>
        <div id="colMetaList">
          ${cols.map((c, i) => `
            <div class="col-meta-card" data-cid="${c.id}">
              <div class="col-meta-head" data-toggle="${c.id}">
                <div style="display:flex;align-items:center;gap:10px;min-width:0">
                  <span class="mono" style="font-weight:700">${esc(c.column_name)}</span>
                  <span class="muted" style="font-size:.75rem">${esc(c.data_type || "")}</span>
                  ${c.is_pk ? '<span class="badge healthy">PK</span>' : ''}
                  ${c.is_pii ? '<span class="badge critical">PII</span>' : ''}
                  ${c.is_measure ? '<span class="badge info">Measure</span>' : ''}
                  ${c.is_dimension ? '<span class="badge warning">Dim</span>' : ''}
                </div>
                <span class="muted" style="font-size:.75rem">${esc(c.semantic_type || c.business_name || "—")} ▾</span>
              </div>
              <div class="col-meta-body" id="colBody${c.id}" style="display:none">
                <div class="grid-2">
                  <div class="field"><span>Business name</span>
                    <input data-f="business_name" value="${esc(c.business_name)}" placeholder="نام کسب‌وکاری" /></div>
                  <div class="field"><span>Semantic type</span>
                    <select data-f="semantic_type">
                      ${["","identifier","temporal","measure","categorical","text","numeric","pii","geo","other"].map((o) =>
                        `<option value="${o}" ${(c.semantic_type||"")===o?"selected":""}>${o || "—"}</option>`).join("")}
                    </select>
                  </div>
                </div>
                <div class="field"><span>Description</span>
                  <textarea data-f="description" rows="2" style="width:100%;padding:6px">${esc(c.description)}</textarea></div>
                <div class="field"><span>Business definition</span>
                  <textarea data-f="business_definition" rows="2" style="width:100%;padding:6px" placeholder="تعریف کسب‌وکاری دقیق برای AI">${esc(c.business_definition)}</textarea></div>
                <div class="grid-2">
                  <div class="field"><span>Unit</span>
                    <input data-f="unit" value="${esc(c.unit)}" placeholder="kWh, currency, percent, …" /></div>
                  <div class="field"><span>Example value</span>
                    <input data-f="example_value" value="${esc(c.example_value)}" /></div>
                </div>
                <div class="grid-2">
                  <div class="field"><span>Synonyms (با کاما)</span>
                    <input data-f="synonyms" value="${esc(c.synonyms)}" placeholder="مصرف, consumption, usage" /></div>
                  <div class="field"><span>Allowed values (با کاما)</span>
                    <input data-f="allowed_values" value="${esc(c.allowed_values)}" placeholder="active, inactive" /></div>
                </div>
                <div class="field"><span>Calculation formula</span>
                  <input data-f="calculation_formula" value="${esc(c.calculation_formula)}" placeholder="SUM(x) / COUNT(*)" style="direction:ltr;text-align:left" /></div>
                <div class="field"><span>AI notes</span>
                  <textarea data-f="ai_notes" rows="2" style="width:100%;padding:6px" placeholder="نکته برای ایجنت‌ها">${esc(c.ai_notes)}</textarea></div>
                <div style="display:flex;flex-wrap:wrap;gap:14px;margin:10px 0;align-items:center">
                  <label style="display:flex;gap:6px;align-items:center;font-size:.85rem;cursor:pointer">
                    <input type="checkbox" data-f="is_pk" ${c.is_pk ? "checked" : ""} /> PK</label>
                  <label style="display:flex;gap:6px;align-items:center;font-size:.85rem;cursor:pointer">
                    <input type="checkbox" data-f="is_pii" ${c.is_pii ? "checked" : ""} /> PII</label>
                  <label style="display:flex;gap:6px;align-items:center;font-size:.85rem;cursor:pointer">
                    <input type="checkbox" data-f="is_measure" ${c.is_measure ? "checked" : ""} /> Measure</label>
                  <label style="display:flex;gap:6px;align-items:center;font-size:.85rem;cursor:pointer">
                    <input type="checkbox" data-f="is_dimension" ${c.is_dimension ? "checked" : ""} /> Dimension</label>
                  <span class="muted" style="font-size:.75rem;margin-right:auto">nullable: ${c.nullable ? "Yes" : "No"} · null ${c.null_pct ?? "—"}%</span>
                  <button class="btn primary btn-sm" data-csave="${c.id}">ذخیره ستون</button>
                </div>
              </div>
            </div>
          `).join("")}
        </div>
        <div id="aiMetaBox" style="display:none;margin-top:16px">
          <div class="panel-head"><h4>🤖 AI / Agent ready metadata (v2)</h4>
            <button class="btn btn-sm" id="btnCopyAi">کپی JSON</button>
          </div>
          <pre class="ai-meta-box" id="aiMetaPre"></pre>
        </div>
      `;

      // accordion
      ed.querySelectorAll("[data-toggle]").forEach((h) => {
        h.onclick = () => {
          const body = $(`#colBody${h.dataset.toggle}`);
          if (!body) return;
          const open = body.style.display !== "none";
          body.style.display = open ? "none" : "block";
        };
      });

      $("#btnSaveTbl").onclick = async () => {
        await api(`/api/tables/${id}/metadata`, {
          method: "PUT",
          body: JSON.stringify({
            description: $("#tblDesc").value,
            owner: $("#tblOwner").value,
            tags: $("#tblTags").value,
          }),
        });
        toast("Metadata جدول ذخیره شد");
      };
      $("#btnAutoMeta").onclick = async () => {
        toast("در حال تولید متادیتای غنی…");
        const res = await api(`/api/tables/${id}/auto-metadata`, { method: "POST", body: "{}" });
        toast(`خودکار: ${res.columns_updated || 0} ستون غنی شد`);
        openMeta(id);
      };
      $("#btnAiMeta").onclick = async () => {
        try {
          const doc = await api(`/api/tables/${id}/ai-metadata`);
          const box = $("#aiMetaBox");
          const pre = $("#aiMetaPre");
          box.style.display = "block";
          pre.textContent = JSON.stringify(doc, null, 2);
          $("#btnCopyAi").onclick = async () => {
            try {
              await navigator.clipboard.writeText(pre.textContent);
              toast("JSON کپی شد");
            } catch { toast("کپی دستی از باکس", true); }
          };
        } catch (e) { toast(e.message, true); }
      };

      ed.querySelectorAll("[data-csave]").forEach((btn) => {
        btn.onclick = async () => {
          const cid = btn.dataset.csave;
          const card = btn.closest(".col-meta-card");
          if (!card) return;
          const payload = {};
          card.querySelectorAll("[data-f]").forEach((inp) => {
            const f = inp.dataset.f;
            if (inp.type === "checkbox") payload[f] = inp.checked ? 1 : 0;
            else payload[f] = inp.value;
          });
          try {
            await api(`/api/columns/${cid}/metadata`, {
              method: "PUT",
              body: JSON.stringify(payload),
            });
            toast("ستون ذخیره شد ✓");
            // refresh badges on head without full reload
            const head = card.querySelector(".col-meta-head");
            if (head) {
              const badges = [];
              if (payload.is_pk) badges.push('<span class="badge healthy">PK</span>');
              if (payload.is_pii) badges.push('<span class="badge critical">PII</span>');
              if (payload.is_measure) badges.push('<span class="badge info">Measure</span>');
              if (payload.is_dimension) badges.push('<span class="badge warning">Dim</span>');
              const mono = head.querySelector(".mono");
              const typeSpan = head.querySelectorAll(".muted")[0];
              head.querySelectorAll(".badge").forEach((b) => b.remove());
              if (typeSpan) typeSpan.insertAdjacentHTML("afterend", " " + badges.join(" "));
              const right = head.querySelectorAll(".muted");
              if (right.length > 1) right[right.length - 1].textContent = (payload.semantic_type || payload.business_name || "—") + " ▾";
            }
          } catch (e) { toast(e.message, true); }
        };
      });
    };

    el.querySelectorAll("[data-mid]").forEach((n) => {
      n.onclick = () => {
        el.querySelectorAll("[data-mid]").forEach((x) => x.classList.remove("active"));
        n.classList.add("active");
        openMeta(Number(n.dataset.mid));
      };
    });
    $("#metaSearch").oninput = (e) => {
      const q = e.target.value.toLowerCase();
      el.querySelectorAll("[data-mid]").forEach((n) => {
        n.style.display = n.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    };
    const btnPacks = $("#btnApplyPacks");
    if (btnPacks) btnPacks.onclick = async () => {
      try {
        toast("اعمال metadata packs…");
        const r = await api("/api/metadata/apply", { method: "POST", body: JSON.stringify({ all: true }) });
        toast(`جداول: ${r.tables_updated || 0} · ستون‌ها: ${r.columns_updated || 0}`);
        loadMetadata();
      } catch (e) { toast(e.message, true); }
    };
    const btnExp = $("#btnAiExport");
    if (btnExp) btnExp.onclick = async () => {
      try {
        toast("در حال ساخت AI catalog…");
        const doc = await api("/api/metadata/ai-export");
        const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "ai_catalog_export.json";
        a.click();
        toast(`Export شد: ${doc.count} جدول`);
      } catch (e) { toast(e.message, true); }
    };
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}


/* ---------- Quality ---------- */
async function loadQuality() {
  const el = $("#content");
  try {
    const q = await api("/api/quality/by-type");
    const types = q.types || [];
    const by = q.by_type || {};
    const first = types[0] ? types[0].check_type : null;
    el.innerHTML = `
      <div class="kpi-row" style="margin-bottom:14px">
        ${types.map((t) => `
          <div class="kpi ${t.fail ? "red" : t.warn ? "amber" : ""}" data-qtype="${t.check_type}" style="cursor:pointer">
            <div class="label">${t.check_type}</div>
            <div class="value" style="font-size:1.3rem">${t.fail}<span class="muted" style="font-size:.85rem"> fail</span></div>
            <div class="sub">${t.warn} warn · ${t.pass} pass · ${t.total} total</div>
          </div>`).join("") || `<div class="kpi"><div class="label">No checks</div></div>`}
      </div>
      <div class="panel">
        <div class="panel-head">
          <h3 id="qTitle">انتخاب نوع تست</h3>
          <div id="qTabs" style="display:flex;gap:6px">
            <button class="btn btn-sm active" data-qf="fail">🔴 Failures</button>
            <button class="btn btn-sm" data-qf="warn">🟡 Warnings</button>
            <button class="btn btn-sm" data-qf="all">همه</button>
          </div>
        </div>
        <div id="qBody"><p class="muted">روی یک نوع تست در بالا کلیک کنید.</p></div>
      </div>
    `;
    let currentType = first;
    let filter = "fail";
    const render = () => {
      if (!currentType || !by[currentType]) {
        $("#qBody").innerHTML = `<p class="muted">داده‌ای نیست</p>`;
        return;
      }
      $("#qTitle").textContent = currentType;
      const bucket = by[currentType];
      let rows = filter === "fail" ? bucket.fail : filter === "warn" ? bucket.warn : bucket.all;
      $("#qBody").innerHTML = `
        <div class="table-wrap"><table>
          <thead><tr><th>DB</th><th>Table</th><th>Metric</th><th>Value</th><th>Threshold</th><th>Status</th><th>When</th></tr></thead>
          <tbody>
            ${(rows || []).map((f) => `
              <tr>
                <td>${f.db_name || ""}</td>
                <td class="mono">${f.table_name}</td>
                <td>${f.metric || ""}</td>
                <td><b>${f.value}</b></td>
                <td>${f.threshold ?? "—"}</td>
                <td>${badge(f.status)}</td>
                <td>${f.check_time || ""}</td>
              </tr>`).join("") || `<tr><td colspan="7" class="muted">موردی در این فیلتر نیست</td></tr>`}
          </tbody>
        </table></div>`;
    };
    el.querySelectorAll("[data-qtype]").forEach((k) => {
      k.onclick = () => {
        currentType = k.dataset.qtype;
        el.querySelectorAll("[data-qtype]").forEach((x) => x.style.outline = "");
        k.style.outline = "2px solid #8b5cf6";
        render();
      };
    });
    el.querySelectorAll("[data-qf]").forEach((b) => {
      b.onclick = () => {
        filter = b.dataset.qf;
        el.querySelectorAll("[data-qf]").forEach((x) => x.classList.toggle("active", x === b));
        render();
      };
    });
    if (first) {
      const k = el.querySelector(`[data-qtype="${first}"]`);
      if (k) k.click();
    }
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}


/* ---------- Profiler ---------- */
async function loadProfiler() {
  const el = $("#content");
  try {
    const tree = await api("/api/catalog");
    const options = [];
    tree.forEach((db) => db.schemas.forEach((sc) => sc.tables.forEach((t) => {
      options.push({ id: t.id, label: `${db.name}.${sc.name}.${t.name}` });
    })));
    el.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <h3>📊 Select a table to profile</h3>
        </div>
        <div class="field">
          <span>Table</span>
          <select id="profTable">
            ${options.map((o) => `<option value="${o.id}">${o.label}</option>`).join("")}
          </select>
        </div>
        <button class="btn primary" id="btnProfile">Run Profile</button>
      </div>
      <div id="profOut"></div>
    `;
    $("#btnProfile").onclick = async () => {
      const id = Number($("#profTable").value);
      const out = $("#profOut");
      out.innerHTML = `<div class="empty">Profiling…</div>`;
      try {
        const p = await api(`/api/profiler/${id}`);
        out.innerHTML = `
          <div class="panel">
            <h3>${p.table.table_name}</h3>
            <div class="grid-kpi">
              <div class="kpi"><div class="label">Rows</div><div class="value" style="font-size:1.2rem">${fmtNum(p.summary.rows)}</div></div>
              <div class="kpi cyan"><div class="label">Columns</div><div class="value" style="font-size:1.2rem">${p.summary.columns}</div></div>
              <div class="kpi amber"><div class="label">Null Records</div><div class="value" style="font-size:1.2rem">${p.summary.null_records_pct}%</div></div>
              <div class="kpi red"><div class="label">Duplicates</div><div class="value" style="font-size:1.2rem">${p.summary.duplicate_records_pct}%</div></div>
            </div>
            <div class="table-wrap"><table>
              <thead><tr><th>Column</th><th>Type</th><th>Null%</th><th>Distinct%</th><th>Min</th><th>Max</th><th>Mean</th><th>Example</th></tr></thead>
              <tbody>
                ${p.column_profiles.map((c) => `
                  <tr>
                    <td class="mono">${c.name}</td><td>${c.type}</td>
                    <td>${c.null_pct}</td><td>${c.distinct_pct}</td>
                    <td>${c.min ?? "—"}</td><td>${c.max ?? "—"}</td>
                    <td>${c.mean ?? "—"}</td><td class="mono">${c.example || "—"}</td>
                  </tr>`).join("")}
              </tbody>
            </table></div>
            <div id="chartHist" class="chart" style="margin-top:16px"></div>
          </div>`;
        safePlot("chartHist", [{
          type: "bar",
          x: p.histogram.map((h) => h.bucket),
          y: p.histogram.map((h) => h.count),
          marker: { color: "#8b5cf6" },
        }], {
          title: { text: "Value distribution (sample)", font: { color: "#94a3b8", size: 13 } },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: "#94a3b8" },
          margin: { t: 40, b: 60, l: 50, r: 20 },
          xaxis: { gridcolor: "rgba(148,163,184,.08)" },
          yaxis: { gridcolor: "rgba(148,163,184,.08)" },
        }, { displayModeBar: false, responsive: true });
      } catch (e) {
        out.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
      }
    };
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

/* ---------- Spark ---------- */


/* ---------- BI Studio (native) ---------- */
let _bi = null;

async function loadBi() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">در حال بارگذاری BI Studio…</div>`;
  let tables = [];
  try {
    const res = await api("/api/sql/live-tables");
    tables = res.tables || res.items || [];
    if (!tables.length && Array.isArray(res)) tables = res;
  } catch (e) {
    el.innerHTML = `<div class="empty">خطا در لیست جداول: ${e.message || e}<br><span class="muted">اول از Auto Discovery وصل شو</span></div>`;
    return;
  }
  if (!tables.length) {
    el.innerHTML = `<div class="empty">جدولی نیست. از تب Auto Discovery به Postgres وصل شو.</div>`;
    return;
  }

  _bi = {
    tables,
    selected: new Set(),
    fields: {}, // table -> [{name, type}]
    step: 1,
    chartType: "bar",
    shelves: { x: null, y: null, legend: null, yAgg: "sum" },
    widgets: [],
    dragField: null,
    widgetSeq: 1,
  };

  el.innerHTML = `
  <div class="bi-studio" id="biStudio">
    <div class="bi-lib" id="biLib">
      <div class="bi-hero">
        <div>
          <h3 style="margin:0">داشبوردهای ذخیره‌شده</h3>
          <p class="muted" style="margin:6px 0 0">باز کردن، ویرایش، حذف یا ساخت داشبورد جدید</p>
        </div>
        <button class="btn primary" id="biNewDash">＋ داشبورد جدید</button>
      </div>
      <div id="biLibList" class="bi-lib-list"><div class="muted">در حال بارگذاری…</div></div>
    </div>
    <div class="bi-step1 hidden" id="biStep1">
      <div class="bi-hero">
        <div>
          <h3 style="margin:0">انتخاب جداول</h3>
          <p class="muted" style="margin:6px 0 0">یک یا چند جدول را انتخاب کن؛ بعد به بوم طراحی می‌رویم</p>
        </div>
        <button class="btn primary" id="biGoDesign" disabled>ادامه · طراحی نمودار ←</button>
      </div>
      <div class="bi-table-grid" id="biTableGrid"></div>
    </div>
    <div class="bi-workspace hidden" id="biWorkspace">
      <aside class="bi-side" id="biSide">
        <div class="bi-side-head">
          <button class="btn ghost btn-sm" id="biBackTables">← جداول</button>
          <strong>فیلدها</strong>
        </div>
        <div class="bi-fields" id="biFields"></div>
        <div class="bi-aggs">
          <div class="muted tiny">تابع تجمیع (Y)</div>
          <div class="bi-agg-row" id="biAggRow">
            ${["sum","avg","count","min","max","count_distinct"].map(a =>
              `<button type="button" class="bi-agg ${a==="sum"?"active":""}" data-agg="${a}">${a}</button>`
            ).join("")}
          </div>
        </div>
      </aside>
      <div class="bi-main">
        <div class="bi-topbar">
          <div class="bi-topbar-left">
            <button type="button" class="bi-icon-btn" id="biBackLib" title="کتابخانه">←</button>
            <span class="bi-dash-name" id="biDashName">داشبورد بدون نام</span>
          </div>
          <div class="bi-chart-types" id="biChartTypes"></div>
          <div class="bi-topbar-right">
            <button type="button" class="bi-icon-btn bi-accent" id="biRender" title="رسم روی بوم">＋ رسم</button>
            <button type="button" class="bi-icon-btn bi-ok" id="biSaveDash" title="ذخیره">💾</button>
            <button type="button" class="bi-icon-btn bi-cyan" id="biExportPdf" title="دانلود PDF">⬇</button>
            <button type="button" class="bi-icon-btn" id="biClearCanvas" title="پاک‌سازی بوم">⌫</button>
          </div>
        </div>
        <div class="bi-shelves" id="biShelves">
          <div class="bi-shelf" data-shelf="x"><span class="bi-shelf-label">محور X · بعد</span><div class="bi-shelf-drop" id="shelfX"><span class="ph">فیلد را بکش اینجا</span></div></div>
          <div class="bi-shelf" data-shelf="y"><span class="bi-shelf-label">محور Y · متریک</span><div class="bi-shelf-drop" id="shelfY"><span class="ph">فیلد را بکش اینجا</span></div></div>
          <div class="bi-shelf" data-shelf="legend"><span class="bi-shelf-label">Legend · رنگ</span><div class="bi-shelf-drop" id="shelfLegend"><span class="ph">اختیاری</span></div></div>
        </div>
        <div class="bi-canvas" id="biCanvas"></div>
      </div>
    </div>
  </div>`;

  const grid = $("#biTableGrid");
  tables.forEach((t, i) => {
    const name = t.table || t.name || t.table_name;
    const schema = t.schema || t.schema_name || "public";
    const rows = t.rows ?? t.row_count ?? "—";
    const card = document.createElement("button");
    card.type = "button";
    card.className = "bi-table-card";
    card.dataset.table = name;
    card.dataset.schema = schema;
    card.innerHTML = `
      <div class="bi-tc-icon">▦</div>
      <div class="bi-tc-body">
        <div class="bi-tc-name">${name}</div>
        <div class="bi-tc-meta">${schema} · ${rows} rows</div>
      </div>
      <div class="bi-tc-check">✓</div>`;
    card.addEventListener("click", () => {
      const key = `${schema}.${name}`;
      if (_bi.selected.has(key)) {
        _bi.selected.delete(key);
        card.classList.remove("selected");
      } else {
        _bi.selected.add(key);
        card.classList.add("selected");
      }
      $("#biGoDesign").disabled = _bi.selected.size === 0;
    });
    grid.appendChild(card);
  });

  const CHARTS = [
    { id: "bar", label: "میله‌ای", icon: "▮" },
    { id: "stacked", label: "میله‌ای انباشته", icon: "▦" },
    { id: "hbar", label: "افقی", icon: "▬" },
    { id: "line", label: "خطی", icon: "╱" },
    { id: "area", label: "سطحی", icon: "▃" },
    { id: "pie", label: "دایره‌ای", icon: "●" },
    { id: "donut", label: "دونات", icon: "◎" },
    { id: "scatter", label: "پراکندگی", icon: "⁘" },
    { id: "combo", label: "ترکیبی", icon: "▮╱" },
    { id: "table", label: "جدول", icon: "☰" },
  ];
  const typesEl = $("#biChartTypes");
  CHARTS.forEach((c, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "bi-ctype" + (i === 0 ? " active" : "");
    b.dataset.type = c.id;
    b.innerHTML = `<span>${c.icon}</span><small>${c.label}</small>`;
    b.addEventListener("click", () => {
      typesEl.querySelectorAll(".bi-ctype").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      _bi.chartType = c.id;
    });
    typesEl.appendChild(b);
  });

  $("#biGoDesign").onclick = () => biEnterDesign();
  $("#biBackTables").onclick = () => {
    $("#biWorkspace").classList.add("hidden");
    $("#biStep1").classList.remove("hidden");
  };
  $("#biNewDash").onclick = () => biOpenEditor(null);
  $("#biBackLib").onclick = () => biShowLibrary();
  $("#biSaveDash").onclick = () => biSaveCurrentDashboard();
  biShowLibrary();
  $("#biAggRow").onclick = (e) => {
    const b = e.target.closest("[data-agg]");
    if (!b) return;
    $("#biAggRow").querySelectorAll(".bi-agg").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    _bi.shelves.yAgg = b.dataset.agg;
    biPaintShelves();
  };
  $("#biRender").onclick = () => biAddWidget();
  $("#biClearCanvas").onclick = () => {
    _bi.widgets = [];
    $("#biCanvas").innerHTML = "";
  };
  $("#biExportPdf").onclick = () => biExportDashboardPdf();

  // shelf drop targets
  ["shelfX", "shelfY", "shelfLegend"].forEach((id) => {
    const node = document.getElementById(id);
    node.addEventListener("dragover", (e) => { e.preventDefault(); node.classList.add("dragover"); });
    node.addEventListener("dragleave", () => node.classList.remove("dragover"));
    node.addEventListener("drop", (e) => {
      e.preventDefault();
      node.classList.remove("dragover");
      const raw = e.dataTransfer.getData("text/bi-field");
      if (!raw) return;
      let field;
      try { field = JSON.parse(raw); } catch { return; }
      const shelf = id === "shelfX" ? "x" : id === "shelfY" ? "y" : "legend";
      _bi.shelves[shelf] = field;
      biPaintShelves();
    });
  });
}


async function biExportDashboardPdf() {
  if (!_bi || !(_bi.widgets || []).length) {
    toast("ابتدا حداقل یک نمودار روی بوم بکش", true);
    return;
  }
  toast("در حال آماده‌سازی PDF…");
  const canvasEl = document.getElementById("biCanvas");
  let cw = 1000, ch = 700;
  if (canvasEl) {
    cw = Math.max(canvasEl.scrollWidth || 0, canvasEl.clientWidth || 0, 800);
    ch = Math.max(canvasEl.scrollHeight || 0, canvasEl.clientHeight || 0, 600);
    // expand to fit all widgets
    (_bi.widgets || []).forEach((w) => {
      cw = Math.max(cw, (w.x || 0) + (w.w || 0) + 24);
      ch = Math.max(ch, (w.y || 0) + (w.h || 0) + 24);
    });
  }
  const widgets = [];
  for (const w of _bi.widgets) {
    const body = document.getElementById("biwb-" + w.id);
    let image = null;
    try {
      if (typeof Plotly !== "undefined" && body) {
        const plotDiv = body.querySelector(".js-plotly-plot") || body.firstElementChild;
        if (plotDiv) {
          const iw = Math.max(400, Math.round(w.w || 420));
          const ih = Math.max(260, Math.round((w.h || 300) - 42));
          image = await Plotly.toImage(plotDiv, { format: "png", width: iw * 2, height: ih * 2, scale: 1 });
        }
      }
    } catch (e) {
      console.warn(e);
    }
    if (image) {
      widgets.push({
        title: w.title || w.type,
        image,
        x: w.x || 0,
        y: w.y || 0,
        w: w.w || 420,
        h: w.h || 300,
      });
    }
  }
  if (!widgets.length) {
    toast("نتوانست تصویر نمودارها را بگیرد", true);
    return;
  }
  try {
    const res = await api("/api/bi/export-pdf", {
      method: "POST",
      body: JSON.stringify({
        title: _bi.dashboardName || "Data Observatory — BI Dashboard",
        canvas: { width: cw, height: ch },
        widgets,
      }),
    });
    if (!res || res.ok === false) {
      toast((res && res.error) || "خطای PDF", true);
      return;
    }
    const a = document.createElement("a");
    a.href = res.url || ("/api/bi/exports/" + res.filename);
    a.download = res.filename || "dashboard.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast("PDF آماده شد");
  } catch (e) {
    toast(String(e.message || e), true);
  }
}


async function biShowLibrary() {
  const lib = $("#biLib");
  if (!lib) return;
  lib.classList.remove("hidden");
  $("#biStep1")?.classList.add("hidden");
  $("#biWorkspace")?.classList.add("hidden");
  const list = $("#biLibList");
  list.innerHTML = `<div class="muted">بارگذاری…</div>`;
  try {
    const r = await api("/api/bi/dashboards");
    const items = r.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="empty">هنوز داشبوردی ذخیره نشده. «داشبورد جدید» را بزن.</div>`;
      return;
    }
    list.innerHTML = `<div class="bi-lib-grid">${items.map((d) => `
      <div class="bi-lib-card" data-id="${d.id}">
        <div class="bi-lib-icon">📐</div>
        <div class="bi-lib-body">
          <div class="bi-lib-name">${(d.name || "Dashboard").replace(/</g, "")}</div>
          <div class="bi-lib-meta">#${d.id} · ${d.updated_at || d.created_at || "—"}</div>
        </div>
        <div class="bi-lib-actions">
          <button type="button" class="btn btn-sm primary" data-open="${d.id}">باز کردن</button>
          <button type="button" class="btn btn-sm" data-del="${d.id}">حذف</button>
        </div>
      </div>`).join("")}</div>`;
    list.querySelectorAll("[data-open]").forEach((b) => {
      b.onclick = () => biOpenEditor(Number(b.dataset.open));
    });
    list.querySelectorAll("[data-del]").forEach((b) => {
      b.onclick = async () => {
        if (!confirm("حذف این داشبورد؟")) return;
        await api("/api/bi/dashboards/" + b.dataset.del, { method: "DELETE" });
        toast("حذف شد");
        biShowLibrary();
      };
    });
  } catch (e) {
    list.innerHTML = `<div class="empty">${e.message}</div>`;
  }
}

function biOpenEditor(dashId) {
  $("#biLib")?.classList.add("hidden");
  $("#biWorkspace")?.classList.add("hidden");
  $("#biStep1")?.classList.remove("hidden");
  if (!_bi) return;
  _bi.dashboardId = dashId || null;
  _bi.dashboardName = dashId ? _bi.dashboardName : "";
  if (!dashId) {
    _bi.selected = new Set();
    _bi.widgets = [];
    _bi.shelves = { x: null, y: null, legend: null, yAgg: "sum" };
    $("#biCanvas") && ($("#biCanvas").innerHTML = "");
    $$(".bi-table-card").forEach((c) => c.classList.remove("selected"));
    $("#biGoDesign").disabled = true;
    return;
  }
  biLoadDashboard(dashId);
}

async function biLoadDashboard(dashId) {
  try {
    const r = await api("/api/bi/dashboards/" + dashId);
    if (!r.ok) { toast(r.error || "خطا", true); return; }
    _bi.dashboardId = r.id;
    _bi.dashboardName = r.name || "Dashboard";
    const p = r.payload || {};
    // restore selected tables
    _bi.selected = new Set(p.selected || []);
    $$(".bi-table-card").forEach((c) => {
      const key = `${c.dataset.schema}.${c.dataset.table}`;
      c.classList.toggle("selected", _bi.selected.has(key));
    });
    $("#biGoDesign").disabled = _bi.selected.size === 0;
    _bi.shelves = p.shelves || { x: null, y: null, legend: null, yAgg: "sum" };
    _bi.chartType = p.chartType || "bar";
    // enter design and remount widgets from saved queries
    if (_bi.selected.size) {
      await biEnterDesign();
      $("#biCanvas").innerHTML = "";
      _bi.widgets = [];
      const saved = p.widgets || [];
      for (const w of saved) {
        try {
          const res = await api("/api/bi/query", { method: "POST", body: JSON.stringify(w.query || {}) });
          if (!res.ok) continue;
          const widget = {
            id: "w" + (_bi.widgetSeq++),
            type: w.type || "bar",
            x: w.x || 20,
            y: w.y || 20,
            w: w.w || 420,
            h: w.h || 300,
            title: w.title || "chart",
            query: w.query,
            data: res,
          };
          _bi.widgets.push(widget);
          biMountWidget(widget);
        } catch (_) {}
      }
      biPaintShelves();
    }
    const dn = document.getElementById("biDashName");
    if (dn) dn.textContent = _bi.dashboardName;
    toast("داشبورد باز شد: " + _bi.dashboardName);
  } catch (e) {
    toast(e.message, true);
  }
}

async function biSaveCurrentDashboard() {
  if (!_bi) return;
  const name = prompt("نام داشبورد:", _bi.dashboardName || "Dashboard") || "";
  if (!name.trim()) return;
  const payload = {
    selected: Array.from(_bi.selected || []),
    shelves: _bi.shelves,
    chartType: _bi.chartType,
    widgets: (_bi.widgets || []).map((w) => ({
      type: w.type,
      x: w.x, y: w.y, w: w.w, h: w.h,
      title: w.title,
      query: w.query,
    })),
  };
  try {
    const body = { name: name.trim(), payload };
    if (_bi.dashboardId) body.id = _bi.dashboardId;
    const r = await api("/api/bi/dashboards", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!r || r.ok === false) { toast((r && r.error) || "خطای ذخیره", true); return; }
    _bi.dashboardId = r.id;
    _bi.dashboardName = r.name;
    const dn = document.getElementById("biDashName");
    if (dn) dn.textContent = r.name;
    toast("ذخیره شد ✓ #" + r.id);
  } catch (e) {
    toast(String(e.message || e), true);
  }
}

async function biEnterDesign() {
  $("#biStep1").classList.add("hidden");
  $("#biWorkspace").classList.remove("hidden");
  const fieldsRoot = $("#biFields");
  fieldsRoot.innerHTML = `<div class="muted tiny">در حال خواندن ستون‌ها…</div>`;
  _bi.fields = {};
  for (const key of _bi.selected) {
    const [schema, ...rest] = key.split(".");
    const name = rest.join(".") || schema;
    const sch = rest.length ? schema : "public";
    const tname = rest.length ? rest.join(".") : schema;
    try {
      const info = await api(`/api/sql/table/${encodeURIComponent(tname)}/info?schema=${encodeURIComponent(sch)}`);
      const cols = info.columns || info.cols || [];
      _bi.fields[key] = cols.map(c => ({
        name: c.name || c.column_name || c.column,
        type: c.type || c.data_type || "",
        table: tname,
        schema: sch,
      }));
    } catch (e) {
      _bi.fields[key] = [];
    }
  }
  biRenderFields();
  biPaintShelves();
}

function biRenderFields() {
  const root = $("#biFields");
  root.innerHTML = "";
  Object.entries(_bi.fields).forEach(([key, cols]) => {
    const group = document.createElement("div");
    group.className = "bi-field-group";
    group.innerHTML = `<div class="bi-fg-title">${key}</div>`;
    cols.forEach((c) => {
      const chip = document.createElement("div");
      chip.className = "bi-field-chip";
      chip.draggable = true;
      const isNum = /int|num|dec|float|double|real|money|numeric/i.test(c.type);
      chip.innerHTML = `<span class="bi-fdot ${isNum ? "m" : "d"}"></span><span>${c.name}</span><small>${(c.type || "").split("(")[0]}</small>`;
      chip.addEventListener("dragstart", (e) => {
        _bi.dragField = c;
        e.dataTransfer.setData("text/bi-field", JSON.stringify(c));
        e.dataTransfer.effectAllowed = "copy";
        chip.classList.add("dragging");
      });
      chip.addEventListener("dragend", () => chip.classList.remove("dragging"));
      group.appendChild(chip);
    });
    root.appendChild(group);
  });
}

function biPaintShelves() {
  const map = {
    x: ["shelfX", _bi.shelves.x],
    y: ["shelfY", _bi.shelves.y],
    legend: ["shelfLegend", _bi.shelves.legend],
  };
  Object.entries(map).forEach(([k, [id, field]]) => {
    const el = document.getElementById(id);
    if (!field) {
      el.innerHTML = `<span class="ph">${k === "legend" ? "اختیاری" : "فیلد را بکش اینجا"}</span>`;
      return;
    }
    const extra = k === "y" ? ` <em>${_bi.shelves.yAgg}</em>` : "";
    el.innerHTML = `<span class="bi-pill">${field.table}.${field.name}${extra}<button type="button" data-clear="${k}">×</button></span>`;
    el.querySelector("[data-clear]")?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      _bi.shelves[k] = null;
      biPaintShelves();
    });
  });
}

async function biAddWidget() {
  if (!_bi.shelves.y) {
    toast("فیلد محور Y (متریک) لازم است", true);
    return;
  }
  const y = _bi.shelves.y;
  const x = _bi.shelves.x;
  const legend = _bi.shelves.legend;
  const body = {
    table: y.table,
    schema: y.schema || "public",
    dimensions: [],
    measures: [{ column: y.name, agg: _bi.shelves.yAgg || "sum" }],
    limit: 5000,
  };
  if (x) body.dimensions.push(x.name);
  if (legend) body.legend = legend.name;

  let res;
  try {
    res = await api("/api/bi/query", { method: "POST", body: JSON.stringify(body) });
  } catch (e) {
    toast(String(e.message || e), true);
    return;
  }
  if (!res.ok) {
    toast(res.error || "خطای کوئری", true);
    return;
  }

  const id = "w" + (_bi.widgetSeq++);
  const widget = {
    id,
    type: _bi.chartType,
    x: 20 + (_bi.widgets.length % 3) * 30,
    y: 20 + Math.floor(_bi.widgets.length / 3) * 40,
    w: 420,
    h: 300,
    title: `${_bi.shelves.yAgg}(${y.name})` + (x ? ` by ${x.name}` : ""),
    query: body,
    data: res,
  };
  _bi.widgets.push(widget);
  biMountWidget(widget);
}

function biPlotlyColors() {
  return ["#8b5cf6", "#06b6d4", "#22c55e", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6", "#a855f7", "#f97316"];
}

function biBuildPlot(widget) {
  const res = widget.data;
  const rows = res.rows || [];
  const measures = res.measures || [];
  const dims = res.dimensions || [];
  const mAlias = (measures[0] && measures[0].alias) || (measures[0] && measures[0].column);
  const dim0 = dims[0];
  const legend = res.legend;
  const colors = biPlotlyColors();
  const layoutBase = {
    paper_bgcolor: "rgba(15,23,42,0.0)",
    plot_bgcolor: "rgba(15,23,42,0.35)",
    font: { color: "#e2e8f0", family: "Vazirmatn, Tahoma, sans-serif", size: 12 },
    margin: { t: 36, b: 48, l: 52, r: 24 },
    title: { text: widget.title, font: { size: 13, color: "#cbd5e1" } },
    legend: { orientation: "h", y: -0.2 },
    colorway: colors,
  };

  if (widget.type === "table") {
    return { kind: "table", rows, columns: res.columns || [] };
  }

  let data = [];
  if (legend && dim0 && mAlias) {
    const series = {};
    rows.forEach((r) => {
      const s = String(r[legend] ?? "—");
      if (!series[s]) series[s] = { x: [], y: [] };
      series[s].x.push(r[dim0]);
      series[s].y.push(Number(r[mAlias]) || 0);
    });
    Object.keys(series).forEach((s, i) => {
      const tr = series[s];
      if (widget.type === "line" || widget.type === "area" || widget.type === "combo") {
        data.push({
          type: "scatter", mode: "lines+markers", name: s,
          x: tr.x, y: tr.y,
          line: { width: 3, color: colors[i % colors.length] },
          fill: widget.type === "area" ? "tozeroy" : undefined,
          fillcolor: widget.type === "area" ? colors[i % colors.length] + "33" : undefined,
        });
      } else if (widget.type === "scatter") {
        data.push({ type: "scatter", mode: "markers", name: s, x: tr.x, y: tr.y,
          marker: { size: 10, color: colors[i % colors.length] } });
      } else if (widget.type === "hbar") {
        data.push({ type: "bar", orientation: "h", name: s, y: tr.x, x: tr.y,
          marker: { color: colors[i % colors.length] } });
      } else {
        data.push({
          type: "bar", name: s, x: tr.x, y: tr.y,
          marker: { color: colors[i % colors.length] },
        });
      }
    });
    if (widget.type === "stacked") layoutBase.barmode = "stack";
    else if (widget.type === "bar" || widget.type === "combo") layoutBase.barmode = "group";
  } else {
    const xs = dim0 ? rows.map(r => r[dim0]) : rows.map((_, i) => i + 1);
    const ys = rows.map(r => Number(r[mAlias]) || 0);
    if (widget.type === "pie" || widget.type === "donut") {
      data = [{
        type: "pie", labels: xs.map(String), values: ys,
        hole: widget.type === "donut" ? 0.55 : 0,
        marker: { colors },
        textinfo: "label+percent",
      }];
      layoutBase.showlegend = true;
    } else if (widget.type === "line" || widget.type === "area" || widget.type === "combo") {
      data = [{
        type: "scatter", mode: "lines+markers", x: xs, y: ys, name: mAlias,
        line: { width: 3, color: colors[0] },
        fill: widget.type === "area" ? "tozeroy" : undefined,
        fillcolor: widget.type === "area" ? colors[0] + "33" : undefined,
        marker: { size: 8, color: colors[1] },
      }];
      if (widget.type === "combo") {
        data.push({ type: "bar", x: xs, y: ys, name: mAlias + " bar", marker: { color: colors[2] + "99" }, opacity: 0.5 });
      }
    } else if (widget.type === "scatter") {
      data = [{ type: "scatter", mode: "markers", x: xs, y: ys,
        marker: { size: 11, color: ys, colorscale: "Viridis", showscale: true } }];
    } else if (widget.type === "hbar") {
      data = [{ type: "bar", orientation: "h", y: xs, x: ys, marker: { color: colors[0] } }];
    } else {
      data = [{
        type: "bar", x: xs, y: ys,
        marker: {
          color: ys,
          colorscale: [[0, "#06b6d4"], [0.5, "#8b5cf6"], [1, "#ec4899"]],
          line: { width: 0 },
        },
      }];
      if (widget.type === "stacked") layoutBase.barmode = "stack";
    }
  }
  return { kind: "plotly", data, layout: layoutBase };
}

function biMountWidget(widget) {
  const canvas = $("#biCanvas");
  const card = document.createElement("div");
  card.className = "bi-widget";
  card.id = "biw-" + widget.id;
  card.style.left = widget.x + "px";
  card.style.top = widget.y + "px";
  card.style.width = widget.w + "px";
  card.style.height = widget.h + "px";
  card.innerHTML = `
    <div class="bi-w-head">
      <span class="bi-w-title">${widget.title}</span>
      <div class="bi-w-actions">
        <button type="button" data-act="refresh" title="بروز">↻</button>
        <button type="button" data-act="close" title="حذف">×</button>
      </div>
    </div>
    <div class="bi-w-body" id="biwb-${widget.id}"></div>
    <div class="bi-w-resize" data-resize="1"></div>`;
  canvas.appendChild(card);

  // drag move
  const head = card.querySelector(".bi-w-head");
  let moving = false, ox = 0, oy = 0;
  head.addEventListener("mousedown", (e) => {
    if (e.target.closest("button")) return;
    moving = true;
    ox = e.clientX - card.offsetLeft;
    oy = e.clientY - card.offsetTop;
    card.classList.add("dragging");
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!moving) return;
    widget.x = Math.max(0, e.clientX - ox);
    widget.y = Math.max(0, e.clientY - oy);
    card.style.left = widget.x + "px";
    card.style.top = widget.y + "px";
  });
  window.addEventListener("mouseup", () => {
    if (moving) {
      moving = false;
      card.classList.remove("dragging");
    }
  });

  // resize
  const rz = card.querySelector("[data-resize]");
  let resizing = false, sx = 0, sy = 0, sw = 0, sh = 0;
  rz.addEventListener("mousedown", (e) => {
    resizing = true;
    sx = e.clientX; sy = e.clientY;
    sw = card.offsetWidth; sh = card.offsetHeight;
    e.preventDefault();
    e.stopPropagation();
  });
  window.addEventListener("mousemove", (e) => {
    if (!resizing) return;
    widget.w = Math.max(280, sw + (e.clientX - sx));
    widget.h = Math.max(200, sh + (e.clientY - sy));
    card.style.width = widget.w + "px";
    card.style.height = widget.h + "px";
    biPaintWidgetBody(widget);
  });
  window.addEventListener("mouseup", () => { resizing = false; });

  card.querySelector('[data-act="close"]').onclick = () => {
    _bi.widgets = _bi.widgets.filter(w => w.id !== widget.id);
    card.remove();
  };
  card.querySelector('[data-act="refresh"]').onclick = async () => {
    try {
      const res = await api("/api/bi/query", { method: "POST", body: JSON.stringify(widget.query) });
      if (res.ok) {
        widget.data = res;
        biPaintWidgetBody(widget);
      }
    } catch (e) { toast(String(e), true); }
  };

  biPaintWidgetBody(widget);
}

function biPaintWidgetBody(widget) {
  const body = document.getElementById("biwb-" + widget.id);
  if (!body) return;
  const built = biBuildPlot(widget);
  if (built.kind === "table") {
    const cols = built.columns.length ? built.columns : (built.rows[0] ? Object.keys(built.rows[0]) : []);
    let html = `<div class="bi-table-wrap"><table class="bi-data-table"><thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>`;
    built.rows.slice(0, 200).forEach(r => {
      html += `<tr>${cols.map(c => `<td>${r[c] ?? ""}</td>`).join("")}</tr>`;
    });
    html += `</tbody></table></div>`;
    body.innerHTML = html;
    return;
  }
  body.innerHTML = "";
  const div = document.createElement("div");
  div.style.width = "100%";
  div.style.height = "100%";
  body.appendChild(div);
  if (typeof Plotly !== "undefined") {
    Plotly.newPlot(div, built.data, built.layout, { responsive: true, displayModeBar: false });
  } else if (typeof safePlot === "function") {
    safePlot(div, built.data, built.layout);
  } else {
    body.innerHTML = `<div class="muted">Plotly در دسترس نیست</div>`;
  }
}


async function loadSql() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">Loading SQL Studio…</div>`;

  let liveTables = [];
  let history = [];
  try {
    const [lt, hist] = await Promise.all([
      api("/api/sql/live-tables"),
      api("/api/sql/history?limit=30"),
    ]);
    liveTables = (lt.tables || []);
    history = hist || [];
  } catch (e) {
    el.innerHTML = `<div class="panel"><p style="color:#f87171">${e.message}</p></div>`;
    return;
  }

  const bySchema = {};
  liveTables.forEach((t) => {
    const sc = t.schema || "public";
    if (!bySchema[sc]) bySchema[sc] = [];
    bySchema[sc].push(t);
  });

  el.innerHTML = `
  <div class="sqlx">
    <aside class="sqlx-side">
      <div class="sqlx-side-hd">
        <strong>جداول</strong>
        <button class="btn btn-sm" id="sqlxRefresh">↻</button>
      </div>
      <input class="sqlx-search" id="sqlxSearch" placeholder="جستجوی جدول…" />
      <div class="sqlx-tree" id="sqlxTree">
        ${Object.keys(bySchema).sort().map((sc) => `
          <div class="sqlx-schema">
            <div class="sqlx-schema-title">📂 ${sc}</div>
            ${bySchema[sc].map((t) => `
              <div class="sqlx-table" data-name="${t.name}" data-schema="${sc}" title="دوبار کلیک = مشاهده داده">
                <span class="sqlx-tname">🗃️ ${t.name}</span>
                <span class="sqlx-meta">${t.size_pretty || (t.rows != null ? t.rows + " rows" : "")}</span>
              </div>
            `).join("")}
          </div>
        `).join("") || `<div class="muted" style="padding:12px">جدولی نیست — Discovery بزن</div>`}
      </div>
      <div class="muted" style="padding:6px 10px;font-size:.7rem;border-top:1px solid rgba(148,163,184,.1)">دابل‌کلیک: Data · راست‌کلیک: Info</div>
      <div class="sqlx-side-hd" style="margin-top:4px"><strong>History</strong></div>
      <div class="sqlx-hist" id="sqlxHist">
        ${(history || []).slice(0, 20).map((h) => `
          <div class="sqlx-hist-item" data-sql="${(h.sql_text || "").replace(/"/g, "&quot;").replace(/</g, "&lt;")}">
            <div class="mono">${(h.sql_text || "").slice(0, 48).replace(/</g, "&lt;")}…</div>
            <span class="tag">${h.status || ""} · ${h.duration_ms || 0}ms</span>
          </div>
        `).join("") || `<div class="muted" style="padding:8px;font-size:.78rem">خالی</div>`}
      </div>
    </aside>

    <div class="sqlx-main">
      <div class="sqlx-tabs" id="sqlxTabs">
        <button class="sqlx-tab active" data-tab="query">Query</button>
        <button class="sqlx-tab" data-tab="data" id="sqlxTabData" disabled>Data</button>
        <button class="sqlx-tab" data-tab="info" id="sqlxTabInfo" disabled>Info</button>
      </div>

      <div class="sqlx-pane active" id="sqlxPaneQuery">
        <div class="sqlx-toolbar">
          <button class="btn primary" id="sqlxRun">▶ Run</button>
          <button class="btn" id="sqlxFormat">Format</button>
          <button class="btn" id="sqlxClear">Clear</button>
          <label class="muted" style="font-size:.78rem;display:flex;gap:6px;align-items:center">
            Limit <input id="sqlxLimit" type="number" value="200" min="1" max="5000" style="width:72px;padding:5px 8px" />
          </label>
          <label class="muted" style="font-size:.78rem;display:flex;gap:6px;align-items:center">
            Engine
            <select id="sqlxEngine" style="padding:5px 8px">
              <option value="postgres">PostgreSQL</option>
              <option value="meta">Observatory Meta</option>
            </select>
          </label>
          <span class="muted" id="sqlxMeta" style="margin-right:auto;font-size:.78rem"></span>
        </div>
        <textarea id="sqlxText" class="sqlx-editor" spellcheck="false" placeholder="SELECT * FROM income_statements LIMIT 50;"></textarea>
        <div class="sqlx-result-hd">
          <span>Results</span>
          <span class="muted" id="sqlxResMeta"></span>
        </div>
        <div class="sqlx-result" id="sqlxResult">
          <div class="muted" style="padding:20px;text-align:center">نتیجه کوئری اینجا نمایش داده می‌شود · Ctrl+Enter</div>
        </div>
      </div>

      <div class="sqlx-pane" id="sqlxPaneData">
        <div class="sqlx-toolbar">
          <strong id="sqlxDataTitle" class="mono">—</strong>
          <button class="btn btn-sm" id="sqlxDataPrev">← Prev</button>
          <button class="btn btn-sm" id="sqlxDataNext">Next →</button>
          <span class="muted" id="sqlxDataPage" style="font-size:.78rem"></span>
          <button class="btn btn-sm" id="sqlxDataRefresh">↻</button>
        </div>
        <div class="sqlx-result" id="sqlxDataGrid"></div>
      </div>

      <div class="sqlx-pane" id="sqlxPaneInfo">
        <div class="sqlx-toolbar"><strong id="sqlxInfoTitle" class="mono">—</strong></div>
        <div id="sqlxInfoBody" style="padding:12px;overflow:auto;flex:1"></div>
      </div>
    </div>
  </div>`;

  let selected = { name: null, schema: "public" };
  let dataOffset = 0;
  const pageSize = 100;

  const showTab = (name) => {
    $$(".sqlx-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    $$(".sqlx-pane").forEach((p) => p.classList.remove("active"));
    const map = { query: "sqlxPaneQuery", data: "sqlxPaneData", info: "sqlxPaneInfo" };
    const pane = document.getElementById(map[name]);
    if (pane) pane.classList.add("active");
  };
  $$(".sqlx-tab").forEach((t) => {
    t.onclick = () => {
      if (t.disabled) return;
      showTab(t.dataset.tab);
    };
  });

  const renderGrid = (columns, rows, mountId) => {
    const mount = document.getElementById(mountId);
    if (!columns || !columns.length) {
      mount.innerHTML = `<div class="muted" style="padding:16px">بدون ستون/داده</div>`;
      return;
    }
    const head = columns.map((c) => `<th>${c}</th>`).join("");
    const body = (rows || []).map((r) =>
      `<tr>${columns.map((c) => {
        let v = r[c];
        if (v == null) return `<td class="muted">NULL</td>`;
        const s = String(v);
        return `<td title="${s.replace(/"/g, "&quot;")}">${s.length > 120 ? s.slice(0, 120) + "…" : s}</td>`;
      }).join("")}</tr>`
    ).join("");
    mount.innerHTML = `<div class="table-wrap sqlx-grid"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  };

  const openTableData = async (name, schema, offset = 0) => {
    selected = { name, schema };
    dataOffset = offset;
    $("#sqlxTabData").disabled = false;
    $("#sqlxTabInfo").disabled = false;
    $("#sqlxDataTitle").textContent = `${schema}.${name}`;
    showTab("data");
    $("#sqlxDataGrid").innerHTML = `<div class="empty">Loading…</div>`;
    try {
      const r = await api(`/api/sql/table/${encodeURIComponent(name)}/data?schema=${encodeURIComponent(schema)}&offset=${offset}&limit=${pageSize}`);
      if (!r.ok) {
        $("#sqlxDataGrid").innerHTML = `<p style="color:#f87171;padding:12px">${r.error}</p>`;
        return;
      }
      renderGrid(r.columns, r.rows, "sqlxDataGrid");
      const from = r.total ? offset + 1 : 0;
      const to = Math.min(offset + (r.rows || []).length, r.total || 0);
      $("#sqlxDataPage").textContent = `${from}–${to} از ${r.total || 0}`;
    } catch (e) {
      $("#sqlxDataGrid").innerHTML = `<p style="color:#f87171;padding:12px">${e.message}</p>`;
    }
  };

  const openTableInfo = async (name, schema) => {
    selected = { name, schema };
    $("#sqlxTabData").disabled = false;
    $("#sqlxTabInfo").disabled = false;
    $("#sqlxInfoTitle").textContent = `${schema}.${name}`;
    showTab("info");
    $("#sqlxInfoBody").innerHTML = `<div class="empty">Loading info…</div>`;
    try {
      const r = await api(`/api/sql/table/${encodeURIComponent(name)}/info?schema=${encodeURIComponent(schema)}`);
      if (!r.ok) {
        $("#sqlxInfoBody").innerHTML = `<p style="color:#f87171">${r.error}</p>`;
        return;
      }
      const sz = r.size || {};
      let html = `<div class="grid-kpi" style="margin-bottom:14px">
        <div class="kpi"><div class="label">حجم کل</div><div class="value" style="font-size:1rem">${sz.total_pretty || "—"}</div></div>
        <div class="kpi cyan"><div class="label">Approx rows</div><div class="value" style="font-size:1rem">${sz.rows_est != null ? Number(sz.rows_est).toLocaleString() : "—"}</div></div>
        <div class="kpi amber"><div class="label">Table bytes</div><div class="value" style="font-size:1rem">${sz.table_bytes != null ? Number(sz.table_bytes).toLocaleString() : "—"}</div></div>
        <div class="kpi green"><div class="label">Index bytes</div><div class="value" style="font-size:1rem">${sz.index_bytes != null ? Number(sz.index_bytes).toLocaleString() : "—"}</div></div>
      </div>`;
      html += `<h4>Primary Key</h4><p class="mono">${(r.primary_key || []).join(", ") || "—"}</p>`;
      html += `<h4>Columns</h4><div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Nullable</th><th>Default</th></tr></thead><tbody>`;
      (r.columns || []).forEach((c) => {
        html += `<tr><td class="mono">${c.column_name}</td><td>${c.data_type}${c.character_maximum_length ? "(" + c.character_maximum_length + ")" : ""}</td><td>${c.is_nullable}</td><td class="mono">${c.column_default || "—"}</td></tr>`;
      });
      html += `</tbody></table></div>`;
      html += `<h4>Foreign Keys</h4>`;
      if ((r.foreign_keys || []).length) {
        html += `<div class="table-wrap"><table><thead><tr><th>Column</th><th>References</th><th>Constraint</th></tr></thead><tbody>`;
        r.foreign_keys.forEach((f) => {
          html += `<tr><td class="mono">${f.column_name}</td><td class="mono">${f.foreign_table_schema}.${f.foreign_table_name}.${f.foreign_column_name}</td><td>${f.constraint_name}</td></tr>`;
        });
        html += `</tbody></table></div>`;
      } else html += `<p class="muted">—</p>`;
      html += `<h4>Indexes</h4>`;
      if ((r.indexes || []).length) {
        html += `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Definition</th></tr></thead><tbody>`;
        r.indexes.forEach((ix) => {
          html += `<tr><td class="mono">${ix.indexname}</td><td class="mono" style="font-size:.75rem">${ix.indexdef}</td></tr>`;
        });
        html += `</tbody></table></div>`;
      } else html += `<p class="muted">—</p>`;
      $("#sqlxInfoBody").innerHTML = html;
    } catch (e) {
      $("#sqlxInfoBody").innerHTML = `<p style="color:#f87171">${e.message}</p>`;
    }
  };

  // tree interactions
  const bindTree = () => {
    $$(".sqlx-table").forEach((n) => {
      n.onclick = () => {
        $$(".sqlx-table").forEach((x) => x.classList.remove("active"));
        n.classList.add("active");
        selected = { name: n.dataset.name, schema: n.dataset.schema };
        $("#sqlxTabData").disabled = false;
        $("#sqlxTabInfo").disabled = false;
      };
      n.ondblclick = () => openTableData(n.dataset.name, n.dataset.schema, 0);
      n.oncontextmenu = (e) => {
        e.preventDefault();
        openTableInfo(n.dataset.name, n.dataset.schema);
      };
    });
  };
  bindTree();

  // single click + buttons for info
  // Add quick actions via middle - also put SELECT into editor on Alt+click
  $$(".sqlx-table").forEach((n) => {
    n.addEventListener("click", (e) => {
      if (e.detail === 1) {
        setTimeout(() => {
          if (n.classList.contains("active")) {
            // keep selection
          }
        }, 200);
      }
    });
  });

  // context: right-click opens info - also add small icons via buttons in toolbar when selected
  // Double-click = data, right-click = info. Also: click Query insert
  $$(".sqlx-table").forEach((n) => {
    n.addEventListener("auxclick", () => {});
  });

  // helper: insert select on Enter key when selected? skip

  $("#sqlxDataPrev").onclick = () => {
    if (!selected.name) return;
    dataOffset = Math.max(0, dataOffset - pageSize);
    openTableData(selected.name, selected.schema, dataOffset);
  };
  $("#sqlxDataNext").onclick = () => {
    if (!selected.name) return;
    dataOffset = dataOffset + pageSize;
    openTableData(selected.name, selected.schema, dataOffset);
  };
  $("#sqlxDataRefresh").onclick = () => {
    if (selected.name) openTableData(selected.name, selected.schema, dataOffset);
  };

  // search filter
  $("#sqlxSearch").oninput = () => {
    const q = ($("#sqlxSearch").value || "").toLowerCase();
    $$(".sqlx-table").forEach((n) => {
      n.style.display = !q || n.dataset.name.toLowerCase().includes(q) ? "" : "none";
    });
  };

  $("#sqlxRefresh").onclick = () => loadSql();

  // history click
  $$("#sqlxHist .sqlx-hist-item").forEach((n) => {
    n.onclick = () => {
      const s = n.getAttribute("data-sql") || "";
      $("#sqlxText").value = s.replace(/&quot;/g, '"').replace(/&lt;/g, "<");
      showTab("query");
    };
  });

  // Run query
  const run = async () => {
    const sql = ($("#sqlxText").value || "").trim();
    if (!sql) { toast("کوئری خالی است", true); return; }
    $("#sqlxMeta").textContent = "Running…";
    $("#sqlxResult").innerHTML = `<div class="empty">Executing…</div>`;
    try {
      const r = await api("/api/sql", {
        method: "POST",
        body: JSON.stringify({
          sql,
          limit: Number($("#sqlxLimit").value) || 200,
          engine: $("#sqlxEngine").value || "postgres",
        }),
      });
      if (!r.ok) {
        $("#sqlxMeta").textContent = "Error";
        $("#sqlxResMeta").textContent = "";
        $("#sqlxResult").innerHTML = `<div style="padding:14px;color:#f87171">${r.error || "failed"}${r.hint ? "<br><span class='muted'>" + r.hint + "</span>" : ""}</div>`;
        return;
      }
      $("#sqlxMeta").textContent = `✓ ${r.engine}`;
      $("#sqlxResMeta").textContent = `${r.row_count} rows · ${r.duration_ms} ms`;
      renderGrid(r.columns, r.rows, "sqlxResult");
      // refresh history silently
      try {
        const h = await api("/api/sql/history?limit=30");
        $("#sqlxHist").innerHTML = (h || []).slice(0, 20).map((x) => `
          <div class="sqlx-hist-item" data-sql="${(x.sql_text || "").replace(/"/g, "&quot;")}">
            <div class="mono">${(x.sql_text || "").slice(0, 48).replace(/</g, "&lt;")}…</div>
            <span class="tag">${x.status} · ${x.duration_ms || 0}ms</span>
          </div>`).join("");
        $$("#sqlxHist .sqlx-hist-item").forEach((n) => {
          n.onclick = () => {
            $("#sqlxText").value = (n.getAttribute("data-sql") || "").replace(/&quot;/g, '"');
            showTab("query");
          };
        });
      } catch {}
    } catch (e) {
      $("#sqlxMeta").textContent = "Error";
      $("#sqlxResult").innerHTML = `<div style="padding:14px;color:#f87171">${e.message}</div>`;
    }
  };

  $("#sqlxRun").onclick = run;
  $("#sqlxClear").onclick = () => { $("#sqlxText").value = ""; };
  $("#sqlxFormat").onclick = () => {
    let s = $("#sqlxText").value.replace(/\s+/g, " ").trim();
    ["SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "LIMIT", "LEFT JOIN", "JOIN", "ON", "HAVING", "UNION"].forEach((k) => {
      s = s.replace(new RegExp("\\b" + k + "\\b", "gi"), "\\n" + k);
    });
    // fix the intentional \\n from above - use real newlines
    s = $("#sqlxText").value.replace(/\s+/g, " ").trim();
    ["SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "LIMIT", "LEFT JOIN", "INNER JOIN", "JOIN", "ON", "HAVING"].forEach((k) => {
      const re = new RegExp("\\b" + k + "\\b", "gi");
      s = s.replace(re, "\\n" + k);
    });
    s = s.split("\\n").join("\n");
    $("#sqlxText").value = s.trim();
  };
  $("#sqlxText").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
  });

  // right-click menu alternative: keyboard shortcut - click table then press I for info, D for data
  // Add action buttons when table selected - inject into side
  document.addEventListener("keydown", function sqlKey(e) {
    if (!$("#sqlxTree")) { document.removeEventListener("keydown", sqlKey); return; }
    if (!selected.name) return;
    if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
    if (e.key === "i" || e.key === "I") openTableInfo(selected.name, selected.schema);
    if (e.key === "d" || e.key === "D") openTableData(selected.name, selected.schema, 0);
  });

  // single-click toolbar: also allow "View data" by button near selection
  // On select, put SELECT snippet in editor with button
  $$(".sqlx-table").forEach((n) => {
    n.addEventListener("click", () => {
      // show floating tip once
    });
  });

  // double-click already bound; add explicit info via Alt+dblclick
  $$(".sqlx-table").forEach((n) => {
    n.addEventListener("dblclick", (e) => {
      if (e.altKey) {
        e.preventDefault();
        openTableInfo(n.dataset.name, n.dataset.schema);
      }
    });
  });

  showTab("query");
}

/* ---------- Growth ---------- */
async function loadGrowth() {
  const el = $("#content");
  try {
    const g = await api("/api/growth");
    el.innerHTML = `
      <div class="panel">
        <h3>📈 Largest Tables</h3>
        <div class="table-wrap"><table>
          <thead><tr><th>Table</th><th>Rows</th><th>Size</th><th>Growth %/wk</th><th></th></tr></thead>
          <tbody>
            ${g.top_by_size.map((t) => `
              <tr>
                <td class="mono">${t.table}</td>
                <td>${t.rows_human}</td>
                <td>${t.size_human}</td>
                <td>+${t.growth_rate_pct}%</td>
                <td><button class="btn" data-gid="${t.table_id}">Trend</button></td>
              </tr>`).join("")}
          </tbody>
        </table></div>
      </div>
      <div id="growthOut"></div>
    `;
    el.querySelectorAll("[data-gid]").forEach((btn) => {
      btn.onclick = async () => {
        const id = Number(btn.dataset.gid);
        const out = $("#growthOut");
        const series = await api(`/api/growth?table_id=${id}`);
        out.innerHTML = `
          <div class="panel">
            <div class="panel-head">
              <h3>${series.table_name} — row growth</h3>
              <span class="muted">
                +${series.growth_rate_pct}% / week
                ${series.forecast_days_to_100gb != null ? `· ~${series.forecast_days_to_100gb} days to 100GB` : ""}
              </span>
            </div>
            <div id="chartGrowth" class="chart"></div>
          </div>`;
        safePlot("chartGrowth", [{
          type: "scatter",
          mode: "lines+markers",
          x: series.series.map((s) => s.date),
          y: series.series.map((s) => s.rows),
          line: { color: "#8b5cf6", width: 3 },
          marker: { size: 6, color: "#06b6d4" },
          fill: "tozeroy",
          fillcolor: "rgba(139,92,246,.12)",
        }], {
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: "#94a3b8" },
          margin: { t: 20, b: 40, l: 60, r: 20 },
          xaxis: { gridcolor: "rgba(148,163,184,.08)" },
          yaxis: { gridcolor: "rgba(148,163,184,.08)" },
        }, { displayModeBar: false, responsive: true });
      };
    });
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

/* ---------- Alerts ---------- */
async function loadAlerts() {
  const el = $("#content");
  try {
    const rows = await api("/api/alerts");
    el.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <h3>🚨 Alert Center</h3>
          <span class="muted">${rows.filter((a) => a.status === "OPEN").length} open</span>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Severity</th><th>Message</th><th>Table</th><th>Database</th><th>When</th><th>Status</th></tr></thead>
          <tbody>
            ${rows.map((a) => `
              <tr>
                <td>${badge(a.severity === "CRITICAL" ? "critical" : a.severity === "WARNING" ? "warning" : "info")}</td>
                <td>${a.message}</td>
                <td class="mono">${a.table_name || "—"}</td>
                <td>${a.db_name || "—"}</td>
                <td>${a.created_at}</td>
                <td>${badge(a.status)}</td>
              </tr>`).join("")}
          </tbody>
        </table></div>
      </div>
      <div class="panel">
        <h3>Health Board (lowest scores first)</h3>
        <div id="healthBoard"></div>
      </div>
    `;
    const board = await api("/api/health");
    $("#healthBoard").innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr><th>Table</th><th>DB</th><th>Overall</th><th>Fresh</th><th>Complete</th><th>Dup</th><th>Valid</th><th>Status</th></tr></thead>
        <tbody>
          ${board.map((h) => `
            <tr>
              <td class="mono">${h.table_name}</td>
              <td>${h.db_name}</td>
              <td><b>${h.overall}</b></td>
              <td>${h.freshness}</td>
              <td>${h.completeness}</td>
              <td>${h.duplicates}</td>
              <td>${h.validity}</td>
              <td>${badge(h.status)}</td>
            </tr>`).join("")}
        </tbody>
      </table></div>`;
  } catch (e) {
    el.innerHTML = `<div class="panel"><p class="muted">${e.message}</p></div>`;
  }
}

/* ---------- Discovery ---------- */
async function loadDiscover() {
  const el = $("#content");
  el.innerHTML = `
    <div class="panel">
      <div class="panel-head">
        <h3>🔭 Auto Discovery — PostgreSQL</h3>
        <button class="btn" id="btnClearCat" style="border-color:rgba(239,68,68,.4);color:#f87171">پاک کردن کاتالوگ</button>
      </div>
      <p class="muted">اتصال واقعی به Postgres: schemaها، جدول‌ها، ستون‌ها ثبت می‌شوند. بعد از اسکن، بسته‌های متادیتا از <code>data/metadata/*.json</code> خودکار اعمال می‌شوند.</p>
      <div class="grid-2">
        <label class="field"><span>Host</span><input id="dHost" value="" placeholder="مثلاً 10.0.0.5 یا localhost" /></label>
        <label class="field"><span>Port</span><input id="dPort" type="number" value="5432" /></label>
        <label class="field"><span>Database</span><input id="dDb" value="" placeholder="نام دیتابیس" /></label>
        <label class="field"><span>Type</span>
          <select id="dType"><option>PostgreSQL</option></select>
        </label>
        <label class="field"><span>Username</span><input id="dUser" value="" placeholder="username" /></label>
        <label class="field"><span>Password</span><input id="dPass" type="password" value="" placeholder="password" /></label>
      </div>
      <div class="row-actions" style="margin-top:12px;gap:8px">
        <button class="btn primary" id="btnDiscover">🔍 Scan & Register</button>
        <button class="btn" id="btnApplyMeta">📚 اعمال Metadata Packs</button>
      </div>
    </div>
    <div id="discOut"></div>
  `;
  $("#btnClearCat").onclick = async () => {
    if (!confirm("همه جداول ثبت‌شده در کاتالوگ observatory پاک شود؟")) return;
    try {
      await api("/api/catalog/clear", { method: "POST", body: "{}" });
      toast("کاتالوگ پاک شد");
      $("#discOut").innerHTML = "";
    } catch (e) { toast(e.message, true); }
  };
  $("#btnDiscover").onclick = async () => {
    const out = $("#discOut");
    out.innerHTML = `<div class="empty">Connecting to PostgreSQL… this may take a minute for large catalogs…</div>`;
    try {
      const r = await api("/api/discover", {
        method: "POST",
        body: JSON.stringify({
          host: $("#dHost").value,
          port: Number($("#dPort").value),
          database: $("#dDb").value,
          db_type: $("#dType").value,
          user: $("#dUser").value,
          password: $("#dPass").value,
        }),
      });
      if (!r.ok) {
        out.innerHTML = `<div class="panel"><p style="color:#f87171">${r.error || "failed"}</p></div>`;
        return;
      }
      const meta = r.metadata_applied || {};
      const applied = (meta.packs || []).flatMap((p) => p.applied || []);
      const skipped = (meta.packs || []).flatMap((p) => p.skipped || []);
      const metaHtml = meta.ok !== false ? `
        <h4 style="margin-top:16px">📚 Metadata packs</h4>
        <p class="muted">جداول به‌روز شده: <b>${meta.tables_updated ?? applied.length}</b>
          · ستون‌ها: <b>${meta.columns_updated ?? "—"}</b>
          · فایل‌ها: ${(meta.files_found || []).map((f)=>f.split(/[/\\]/).pop()).join(", ") || "—"}</p>
        ${applied.length ? `<div class="table-wrap"><table>
          <thead><tr><th>Table</th><th>Columns updated</th></tr></thead>
          <tbody>${applied.map((a)=>`<tr><td class="mono">${a.table}</td><td>${a.columns_updated}</td></tr>`).join("")}</tbody>
        </table></div>` : `<p class="muted">هیچ جدولی با packها match نشد. نام جدول در Postgres باید مثل income_statements باشد.</p>`}
        ${skipped.length ? `<p class="muted">رد شده: ${skipped.map((s)=>s.table+" ("+s.reason+")").join(", ")}</p>` : ""}
        ${(meta.errors && meta.errors.length) ? `<p style="color:#f87171">خطاها: ${JSON.stringify(meta.errors)}</p>` : ""}
      ` : `<p style="color:#f87171">اعمال متادیتا ناموفق: ${(meta && meta.error) || "unknown"}</p>`;
      out.innerHTML = `
        <div class="panel" style="border-color:rgba(34,197,94,.35)">
          <h3>✅ ${r.message || "Done"}</h3>
          <div class="grid-kpi">
            <div class="kpi green"><div class="label">Connection</div><div class="value" style="font-size:1.1rem">${r.connection}</div></div>
            <div class="kpi"><div class="label">Schemas</div><div class="value">${r.schemas}</div></div>
            <div class="kpi cyan"><div class="label">Tables</div><div class="value">${r.tables}</div></div>
            <div class="kpi amber"><div class="label">Columns</div><div class="value">${fmtNum(r.columns)}</div></div>
          </div>
          <p class="muted">${r.db_type} @ ${r.host}:${r.port}/${r.database}</p>
          ${metaHtml}
          <p class="muted" style="margin-top:12px">حالا به تب‌های Catalog / Metadata بروید.</p>
        </div>`;
      toast(applied.length ? `کاتالوگ + متادیتا (${applied.length} جدول)` : "کاتالوگ پر شد — متادیتا match نشد");
    } catch (e) {
      out.innerHTML = `<div class="panel"><p style="color:#f87171">${e.message}</p></div>`;
    }
  };

  $("#btnApplyMeta").onclick = async () => {
    const out = $("#discOut");
    out.innerHTML = `<div class="empty">در حال اعمال metadata packs…</div>`;
    try {
      const r = await api("/api/metadata/apply", { method: "POST", body: JSON.stringify({ all: true }) });
      const applied = (r.packs || []).flatMap((p) => p.applied || []);
      out.innerHTML = `<div class="panel">
        <h3>📚 نتیجه اعمال Metadata</h3>
        <p>جداول: <b>${r.tables_updated}</b> · ستون‌ها: <b>${r.columns_updated}</b></p>
        <p class="muted">فایل‌ها: ${(r.files_found || []).join(" | ") || "هیچ JSON پیدا نشد"}</p>
        ${applied.length ? `<div class="table-wrap"><table>
          <thead><tr><th>Table</th><th>Cols</th></tr></thead>
          <tbody>${applied.map((a)=>`<tr><td class="mono">${a.table}</td><td>${a.columns_updated}</td></tr>`).join("")}</tbody>
        </table></div>` : `<p class="muted">ابتدا Discover کنید تا جداول در کاتالوگ باشند، بعد دوباره Apply بزنید.</p>`}
        <pre class="ai-meta-box" style="max-height:200px">${JSON.stringify(r, null, 2)}</pre>
      </div>`;
      toast(r.tables_updated ? "متادیتا اعمال شد" : "جدولی match نشد");
    } catch (e) {
      out.innerHTML = `<div class="panel"><p style="color:#f87171">${e.message}</p></div>`;
    }
  };
}


/* ---------- AI Assistant ---------- */
let _aiHistory = [];

function simpleMarkdown(md) {
  if (!md) return "";
  let s = String(md)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  s = s.replace(/```(?:sql|json|python)?\s*([\s\S]*?)```/g, (_, code) =>
    `<pre class="ai-code">${code.trim()}</pre>`);
  // markdown tables
  s = s.replace(/(?:^\|.+\|[ \t]*\n)+/gm, (block) => {
    const rows = block.trim().split(/\n/).filter(Boolean);
    if (rows.length < 2) return block;
    const cells = (r) => r.split("|").filter((_, i, a) => i > 0 && i < a.length - 1).map((c) => c.trim());
    const head = cells(rows[0]);
    const bodyRows = rows.slice(1).filter((r) => !/^\|?\s*[-:| ]+\s*\|?$/.test(r));
    let html = '<div class="table-wrap"><table><thead><tr>' +
      head.map((h) => `<th>${h}</th>`).join("") + "</tr></thead><tbody>";
    bodyRows.forEach((r) => {
      const cols = cells(r);
      html += "<tr>" + cols.map((c) => `<td>${c}</td>`).join("") + "</tr>";
    });
    return html + "</tbody></table></div>";
  });
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  s = s.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  s = s.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^# (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^\s*[-•]\s+(.+)$/gm, "<li>$1</li>");
  s = s.replace(/(<li>[\s\S]*?<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
  s = s.replace(/\n\n/g, "</p><p>");
  s = s.replace(/\n/g, "<br>");
  return `<div class="ai-md"><p>${s}</p></div>`;
}

async function loadAssistant() {
  const el = $("#content");
  let statusHtml = `<span class="muted">در حال بررسی Ollama…</span>`;
  el.innerHTML = `
    <div class="ai-layout">
      <div class="ai-sidebar panel">
        <div class="panel-head"><h3>🤖 رصدیار</h3></div>
        <div id="aiStatus" class="muted" style="font-size:.82rem;margin-bottom:12px">${statusHtml}</div>
        <div class="eyebrow" style="margin-bottom:6px">نمونه سوالات</div>
        <button class="ai-suggest" data-q="کدام جداول critical هستند از نظر تازگی؟">تازگی · Critical</button>
        <button class="ai-suggest" data-q="خلاصه وضعیت کیفیت داده را بگو">کیفیت داده</button>
        <button class="ai-suggest" data-q="جدول MeterInfo چه ستون‌هایی دارد و کدام‌ها measure هستند؟">متادیتای MeterInfo</button>
        <button class="ai-suggest" data-q="جداول مرتبط با مصرف یا انرژی را پیدا کن">جستجوی کاتالوگ</button>
        <button class="ai-suggest" data-q="میانگین تأخیر جداول چقدر است و نمودار وضعیت تازگی را نشان بده">تحلیل + نمودار</button>
        <button class="btn btn-sm" id="aiClear" style="margin-top:14px;width:100%">🗑️ پاک کردن گفتگو</button>
        <p class="muted" style="font-size:.72rem;margin-top:14px;line-height:1.6">
          منابع تفکیک‌شده:<br>
          • داده → متادیتا + SQL متا<br>
          • تازگی → Freshness API<br>
          • کیفیت → Quality API<br>
          مدل: Ollama لوکال
        </p>
      </div>
      <div class="ai-chat-wrap panel">
        <div id="aiChat" class="ai-chat"></div>
        <div class="ai-input-row">
          <textarea id="aiInput" rows="2" placeholder="مثلاً: سود این ماه چقدر بوده؟ / کدام جدول‌ها stale هستند؟"></textarea>
          <button class="btn primary" id="aiSend">ارسال</button>
        </div>
      </div>
    </div>
  `;

  const chat = $("#aiChat");
  const addBubble = (role, html, charts) => {
    const div = document.createElement("div");
    div.className = "ai-bubble " + (role === "user" ? "user" : "bot");
    div.innerHTML = html;
    chat.appendChild(div);
    if (charts && charts.length) {
      charts.forEach((ch, i) => {
        const cid = "aiChart_" + Date.now() + "_" + i;
        const wrap = document.createElement("div");
        wrap.className = "ai-chart-wrap";
        wrap.style.cssText = "margin:10px 0 16px;min-height:280px;background:rgba(15,23,42,.5);border-radius:12px;padding:8px;";
        wrap.innerHTML = `<div id="${cid}" class="chart chart-tall" style="height:280px;width:100%"></div>`;
        chat.appendChild(wrap);
        const data = (ch && ch.data) || (ch && ch.chart && ch.chart.data);
        const layout = (ch && ch.layout) || (ch && ch.chart && ch.chart.layout) || {};
        if (!data) {
          wrap.innerHTML = `<p class="muted">نمودار: داده خالی</p>`;
          return;
        }
        // wait for layout so Plotly gets non-zero width
        setTimeout(() => {
          try {
            safePlot(cid, data, layout);
          } catch (e) {
            wrap.innerHTML = `<p class="muted">نمودار: ${e.message}</p>`;
          }
        }, 50);
      });
    }
    chat.scrollTop = chat.scrollHeight;
  };

  if (!_aiHistory.length) {
    addBubble("bot", simpleMarkdown(
      "سلام! من **رصدیار** هستم — دستیار Data Observatory.\n\n" +
      "می‌توانی بپرسی:\n" +
      "- سوالات **داده و کاتالوگ** (با متادیتای غنی)\n" +
      "- وضعیت **تازگی / SLA**\n" +
      "- **کیفیت داده** و health\n" +
      "- درخواست **نمودار** و محاسبات\n\n" +
      "اگر متادیتا نباشد از نام جدول و فیلدها استنباط می‌کنم."
    ));
  } else {
    // re-render full history including charts
    _aiHistory.forEach((h) => {
      if (h.role === "user") addBubble("user", h.content.replace(/</g, "&lt;"));
      else addBubble("bot", simpleMarkdown(h.content), h.charts || []);
    });
  }

  try {
    const st = await api("/api/ai/status");
    const box = $("#aiStatus");
    const live = st.live_db
      ? `<div class="muted" style="margin-top:6px">DB: <span class="mono">${st.live_db.host}/${st.live_db.database}</span></div>`
      : `<div class="muted" style="margin-top:6px;color:#f59e0b">ابتدا Auto Discovery بزن</div>`;
    if (st.ok && st.model_ready) {
      box.innerHTML = `<span class="badge healthy">Online</span> <span class="mono">${st.model}</span>${live}`;
    } else if (st.ok) {
      box.innerHTML = `<span class="badge warning">اجرایی</span> <span class="mono">SQL+Python</span>${live}<div class="muted">مدل اختیاری است</div>`;
    } else {
      box.innerHTML = `<span class="badge warning">اجرایی</span> SQL+Python${live}<div class="muted">${(st.error || "").slice(0,80)}</div>`;
    }
  } catch (e) {
    $("#aiStatus").innerHTML = `<span class="badge critical">Error</span> ${e.message}`;
  }

  const send = async () => {
    const input = $("#aiInput");
    const msg = (input.value || "").trim();
    if (!msg) return;
    input.value = "";
    addBubble("user", msg.replace(/</g, "&lt;"));
    _aiHistory.push({ role: "user", content: msg });
    const thinking = document.createElement("div");
    thinking.className = "ai-bubble bot ai-thinking";
    thinking.textContent = "در حال فکر و فراخوانی ابزارها…";
    chat.appendChild(thinking);
    chat.scrollTop = chat.scrollHeight;
    try {
      const res = await api("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message: msg,
          history: _aiHistory.slice(0, -1).map((h) => ({ role: h.role, content: h.content })),
        }),
      });
      thinking.remove();
      const answer = res.answer || JSON.stringify(res);
      const charts = res.charts || [];
      addBubble("bot", simpleMarkdown(answer), charts);
      // keep charts in history so they survive tab switches
      _aiHistory.push({ role: "assistant", content: answer, charts: charts });
      if (res.tools_used && res.tools_used.length) {
        const tools = res.tools_used.map((t) => t.tool).join(" · ");
        const tip = document.createElement("div");
        tip.className = "ai-tools-tip";
        tip.textContent = "ابزارها: " + tools;
        chat.appendChild(tip);
      }
    } catch (e) {
      thinking.remove();
      addBubble("bot", simpleMarkdown("خطا: " + e.message));
    }
  };

  $("#aiSend").onclick = send;
  $("#aiInput").onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };
  $("#aiClear").onclick = () => {
    _aiHistory = [];
    loadAssistant();
  };
  $$(".ai-suggest").forEach((b) => {
    b.onclick = () => {
      $("#aiInput").value = b.dataset.q;
      send();
    };
  });
}


/* ---------- Boot ---------- */
$("#btnScan").onclick = async () => {
  try {
    const r = await api("/api/scan", { method: "POST" });
    toast(`Scan done · ${r.tables} tables`);
    showPage("overview");
  } catch (e) {
    toast(e.message, true);
  }
};

$$("#nav button").forEach((b) => {
  b.addEventListener("click", () => showPage(b.dataset.page));
});

showPage("overview");



/* ---------- Machine Learning Studio (isolated) — RapidMiner-style wizard ---------- */
let _mlState = {
  step: 1,
  table: null,
  table_id: null,
  profile: null,
  target: null,
  task: null,
  model: "RandomForest",
  dataset_path: null,
  experiment_id: null,
  last_train: null,
  history: [],
};

function _mlCtx() {
  return {
    step: _mlState.step,
    table: _mlState.table,
    target: _mlState.target,
    task: _mlState.task,
    model: _mlState.model,
    last_metrics: (_mlState.last_train && _mlState.last_train.metrics) || null,
    last_verdict: (_mlState.last_train && _mlState.last_train.metrics && _mlState.last_train.metrics.verdict) || null,
    target_suggestions: (_mlState.profile && _mlState.profile.target_suggestions) || null,
    experiment_id: _mlState.experiment_id,
  };
}

function _mlVerdictBadge(v) {
  if (!v) return "";
  const t = String(v);
  let cls = "mid";
  if (t.indexOf("خوب") >= 0) cls = "good";
  else if (t.indexOf("ضعیف") >= 0) cls = "bad";
  return `<span class="ml-badge ${cls}">${t}</span>`;
}

async function loadML() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">بارگذاری ML Studio…</div>`;
  let tables = [];
  try {
    const r = await api("/api/ml/tables");
    tables = r.tables || [];
  } catch (e) {
    el.innerHTML = `<div class="panel"><p style="color:#f87171">${e.message}</p></div>`;
    return;
  }

  const opts = tables.map((t) =>
    `<option value="${t.table}" data-id="${t.table_id}">${t.db}.${t.table} (${t.rows || 0} rows)</option>`
  ).join("");

  el.innerHTML = `
  <div class="ml-mode-bar">
    <button class="btn primary" data-mlmode="wizard" id="mlModeWizard">🧙 Wizard</button>
    <button class="btn" data-mlmode="history" id="mlModeHistory">📜 History</button>
    <button class="btn" data-mlmode="pro" id="mlModePro">⚡ PRO Notebook</button>
  </div>
  <div id="mlModeWizardView">
  <div class="ml-wizard">
    <div class="ml-steps" id="mlSteps">
      <div class="ml-step active" data-s="1"><span class="sn">1</span><span class="sl">داده</span></div>
      <div class="ml-step" data-s="2"><span class="sn">2</span><span class="sl">تحلیل</span></div>
      <div class="ml-step" data-s="3"><span class="sn">3</span><span class="sl">آماده‌سازی</span></div>
      <div class="ml-step" data-s="4"><span class="sn">4</span><span class="sl">مدل</span></div>
      <div class="ml-step" data-s="5"><span class="sn">5</span><span class="sl">نتایج</span></div>
      <div class="ml-step" data-s="6"><span class="sn">6</span><span class="sl">بهبود</span></div>
      <div class="ml-step" data-s="7"><span class="sn">7</span><span class="sl">مدل نهایی</span></div>
    </div>

    <!-- Step 1: Data -->
    <div class="panel ml-step-panel active" id="mlPanel1">
      <div class="panel-head"><h3>① انتخاب داده</h3></div>
      <p class="muted">جدول منبع را انتخاب کن. جدول اصلی هرگز تغییر نمی‌کند.</p>
      <label class="field" style="max-width:480px">
        <span>جدول از کاتالوگ</span>
        <select id="mlTable"><option value="">— انتخاب جدول —</option>${opts}</select>
      </label>
      <div class="ml-nav-btns">
        <span></span>
        <button class="btn primary" id="mlGo2">ادامه → تحلیل</button>
      </div>
    </div>

    <!-- Step 2: Analyze -->
    <div class="panel ml-step-panel" id="mlPanel2">
      <div class="panel-head"><h3>② تحلیل داده و متادیتا</h3></div>
      <div id="mlAnalyzeStatus" class="muted">روی «شروع تحلیل» بزن.</div>
      <div id="mlAiText" class="ai-md" style="margin-top:12px"></div>
      <div id="mlSuggestTargets" style="margin-top:12px"></div>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="1">← قبلی</button>
        <div class="row-actions">
          <button class="btn" id="mlRunAnalyze">🔍 شروع تحلیل</button>
          <button class="btn primary" id="mlGo3" disabled>ادامه → آماده‌سازی</button>
        </div>
      </div>
    </div>

    <!-- Step 3: Prepare -->
    <div class="panel ml-step-panel" id="mlPanel3">
      <div class="panel-head"><h3>③ پیش‌پردازش و آماده‌سازی</h3></div>
      <p class="muted">پیشنهادها را بررسی کن. با تأیید، CSV تمیز + VIEW فقط‌خواندنی ساخته می‌شود.</p>
      <div class="grid-2">
        <label class="field"><span>Target (هدف پیش‌بینی)</span><select id="mlTarget"></select></label>
        <label class="field"><span>نوع مسئله</span>
          <select id="mlTask">
            <option value="regression">Regression</option>
            <option value="classification">Classification</option>
          </select>
        </label>
      </div>
      <div id="mlPrepList" style="margin:12px 0"></div>
      <div id="mlPrepOut"></div>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="2">← قبلی</button>
        <div class="row-actions">
          <button class="btn primary" id="mlPrepare">✓ اعمال پیش‌پردازش</button>
          <button class="btn" id="mlGo4" disabled>ادامه → مدل</button>
        </div>
      </div>
    </div>

    <!-- Step 4: Model -->
    <div class="panel ml-step-panel" id="mlPanel4">
      <div class="panel-head"><h3>④ انتخاب مدل</h3></div>
      <p class="muted">مدل‌های پیشنهادی بر اساس نوع مسئله. یکی را انتخاب کن.</p>
      <div id="mlModelCards"></div>
      <label class="field" style="max-width:280px;margin-top:10px">
        <span>یا انتخاب دستی</span>
        <select id="mlModel">
          <option>RandomForest</option>
          <option>GradientBoosting</option>
          <option>XGBoost</option>
          <option>Ridge</option>
          <option>LogisticRegression</option>
        </select>
      </label>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="3">← قبلی</button>
        <button class="btn primary" id="mlGo5">شروع آموزش + GridSearch →</button>
      </div>
    </div>

    <!-- Step 5: Results -->
    <div class="panel ml-step-panel" id="mlPanel5">
      <div class="panel-head"><h3>⑤ نتایج آموزش</h3></div>
      <div id="mlTrainStatus" class="muted"></div>
      <div id="mlMetrics"></div>
      <div id="mlImpChart" class="chart chart-tall" style="height:280px;margin-top:12px"></div>
      <div id="mlAnalysis" class="ai-md" style="margin-top:12px"></div>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="4">← مدل</button>
        <button class="btn primary" id="mlGo6">ادامه → بهبود مدل</button>
      </div>
    </div>

    <!-- Step 6: Improve loop -->
    <div class="panel ml-step-panel" id="mlPanel6">
      <div class="panel-head"><h3>⑥ بهبود تکراری</h3></div>
      <p class="muted">اگر مدل ضعیف/متوسط بود، تغییرات پیشنهادی را اعمال کن و دوباره آموزش بده تا به نتیجه خوب برسی.</p>
      <div id="mlImprovePlan"></div>
      <div id="mlImproveOut" style="margin-top:10px"></div>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="5">← نتایج</button>
        <div class="row-actions">
          <button class="btn primary" id="mlApplyImprove">⚡ اعمال بهبود و آموزش مجدد</button>
          <button class="btn" id="mlFinalize" style="border-color:rgba(34,197,94,.5);color:#4ade80">✓ قبول مدل نهایی</button>
          <button class="btn" id="mlRestart">شروع از اول</button>
        </div>
      </div>
      <div style="margin-top:16px">
        <h4 style="margin:0 0 8px">تاریخچه آزمایش‌ها</h4>
        <div id="mlExpList" class="muted">—</div>
      </div>
    </div>

    <!-- Step 7: Final model -->
    <div class="panel ml-step-panel" id="mlPanel7">
      <div class="panel-head"><h3>⑦ مدل نهایی</h3></div>
      <div id="mlFinalSummary"></div>
      <div id="mlFinalMetrics" style="margin-top:12px"></div>
      <div class="grid-2" style="margin-top:12px;gap:12px">
        <div>
          <h4 style="margin:0 0 8px">Feature Importance</h4>
          <div id="mlFinalImpChart" class="chart chart-tall" style="height:280px"></div>
        </div>
        <div>
          <h4 style="margin:0 0 8px">پیش‌بینی در برابر واقعی</h4>
          <div id="mlFinalPredChart" class="chart chart-tall" style="height:280px"></div>
        </div>
      </div>
      <div id="mlFinalAnalysis" class="ai-md" style="margin-top:14px"></div>
      <div class="panel" style="margin-top:16px;border:1px solid rgba(139,92,246,.25)" id="mlPredictPanel">
        <div class="panel-head"><h3>🔮 استفاده از مدل ذخیره‌شده</h3></div>
        <p class="muted" style="margin:0 0 10px">داده جدید بده (JSON آرایه از آبجکت‌ها) یا از همان dataset آموزش استفاده کن. مدل از joblib لود می‌شود.</p>
        <div class="row-actions" style="margin-bottom:8px;flex-wrap:wrap;gap:8px">
          <button class="btn primary" id="mlPredictRun">▶ پیش‌بینی</button>
          <button class="btn" id="mlPredictDataset">از dataset آموزش</button>
          <button class="btn" id="mlCopyLoadCode">کپی کد لود (Notebook)</button>
        </div>
        <textarea id="mlPredictJson" class="mono" dir="ltr" style="width:100%;min-height:110px;background:#0a0f1c;color:#e2e8f0;border:1px solid rgba(148,163,184,.2);border-radius:10px;padding:10px;font-size:.8rem" placeholder='[{"feature1": 1.2, "feature2": 3}]'></textarea>
        <div id="mlPredictMeta" class="muted tiny" style="margin-top:6px"></div>
        <div id="mlPredictMetrics" style="margin-top:10px"></div>
        <div id="mlPredictChart" class="chart chart-tall" style="height:280px;margin-top:10px"></div>
        <div id="mlPredictTable" style="margin-top:10px;overflow:auto;max-height:260px"></div>
        <pre id="mlPredictSnippet" class="mono" dir="ltr" style="display:none;margin-top:10px;background:#0a0f1c;padding:12px;border-radius:10px;color:#a5f3fc;font-size:.78rem;white-space:pre-wrap"></pre>
      </div>
      <div class="ml-nav-btns">
        <button class="btn" data-mlback="6">← بهبود</button>
        <button class="btn" id="mlRestart2">شروع آزمایش جدید</button>
      </div>
    </div>
  </div>

  </div><!-- /mlModeWizardView -->

  <div id="mlModeHistoryView" style="display:none">
    <div class="panel">
      <div class="panel-head"><h3>📜 تاریخچه مدل‌ها</h3>
        <button class="btn btn-sm" id="mlHistRefresh">↻</button>
      </div>
      <p class="muted">مدل‌های ذخیره‌شده را باز کن — بدون آموزش مجدد.</p>
      <div id="mlHistFull">—</div>
    </div>
  </div>

  <div id="mlModeProView" style="display:none">
    <div class="nb-lib" id="nbLib">
      <div class="bi-hero">
        <div>
          <h3 style="margin:0">نوت‌بوک‌های ذخیره‌شده</h3>
          <p class="muted" style="margin:6px 0 0">باز کردن، ویرایش، حذف یا ساخت نوت‌بوک جدید</p>
        </div>
        <button class="btn primary" id="nbNewNotebook" type="button">＋ نوت‌بوک جدید</button>
      </div>
      <div id="nbLibList" class="bi-lib-list"><div class="muted">—</div></div>
    </div>
    <div class="nb-wrap hidden" id="nbEditor" dir="ltr">
      <div class="nb-toolbar">
        <label class="field" style="min-width:200px;margin:0">
          <span style="font-size:.7rem">جدول منبع</span>
          <select id="nbTable"><option value="">— بدون جدول —</option>${opts}</select>
        </label>
        <button class="btn primary" id="nbStart">▶ Start Kernel</button>
        <button class="btn" id="nbReset" disabled>Reset</button>
        <button class="btn" id="nbAddCell" disabled>+ Cell</button>
        <button class="btn" id="nbSaveNotebook" style="border-color:rgba(34,197,94,.4);color:#4ade80">💾 Save</button>
        <button class="btn" id="nbBackLib">← Library</button>
        <span class="muted" id="nbStatus" style="font-size:.78rem">kernel خاموش</span><span class="muted" style="font-size:.68rem;margin-right:auto">Shift+Enter · Alt+Enter</span>
      </div>
      <div id="nbHints" class="muted" style="font-size:.75rem;padding:4px 2px 10px"></div>
      <div id="nbCells" class="nb-cells"></div>
    </div>
  </div>

  <button type="button" class="ml-chat-fab" id="mlChatFab" title="دستیار ML">💬</button>
  <div class="ml-chat-panel" id="mlChatPanel">
    <div class="hd">
      <h4>دستیار ML</h4>
      <button type="button" id="mlChatClose">✕</button>
    </div>
    <div id="mlChat" class="ai-chat"></div>
    <div class="ai-input-row">
      <textarea id="mlChatInput" rows="2" placeholder="سوال کوتاه…"></textarea>
      <button class="btn primary" id="mlChatSend">ارسال</button>
    </div>
  </div>
  `;

  const goStep = (n) => {
    _mlState.step = n;
    $$(".ml-step-panel").forEach((p) => p.classList.remove("active"));
    const panel = document.getElementById("mlPanel" + n);
    if (panel) panel.classList.add("active");
    $$("#mlSteps .ml-step").forEach((s) => {
      const sn = Number(s.dataset.s);
      s.classList.toggle("active", sn === n);
      s.classList.toggle("done", sn < n);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  $$("#mlSteps .ml-step").forEach((s) => {
    s.onclick = () => {
      const sn = Number(s.dataset.s);
      // allow going back freely; forward only if prerequisites met
      if (sn === 1) goStep(1);
      else if (sn === 2 && _mlState.table) goStep(2);
      else if (sn === 3 && _mlState.profile) goStep(3);
      else if (sn === 4 && _mlState.dataset_path) goStep(4);
      else if (sn === 5 && _mlState.last_train) goStep(5);
      else if (sn === 6 && _mlState.last_train) goStep(6);
      else if (sn === 7 && _mlState.last_train) goStep(7);
    };
  });
  $$("[data-mlback]").forEach((b) => {
    b.onclick = () => goStep(Number(b.dataset.mlback));
  });

  // Compact floating chat
  const chat = $("#mlChat");
  const addChat = (role, html) => {
    const d = document.createElement("div");
    d.className = "ai-bubble " + (role === "user" ? "user" : "bot");
    d.innerHTML = html;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
  };
  addChat("bot", simpleMarkdown("از همین فرایند بپرس — کوتاه و کاربردی جواب می‌دهم."));
  const panel = $("#mlChatPanel");
  $("#mlChatFab").onclick = () => panel.classList.add("open");
  $("#mlChatClose").onclick = () => panel.classList.remove("open");

  const refreshExp = async () => {
    try {
      const r = await api("/api/ml/experiments");
      const list = r.experiments || [];
      if (!list.length) {
        $("#mlExpList").innerHTML = `<span class="muted">هنوز آزمایشی نیست</span>`;
        return;
      }
      $("#mlExpList").innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>جدول</th><th>Target</th><th>Model</th><th>Status</th><th>نتیجه</th><th></th></tr></thead>
        <tbody>${list.map((e) => {
          const m = e.metrics || {};
          const ms = m.verdict || (m.r2 != null ? "r2=" + Number(m.r2).toFixed(3) : null) || (m.f1_weighted != null ? "f1=" + Number(m.f1_weighted).toFixed(3) : "—");
          return `<tr><td>${e.id}</td><td class="mono">${e.table_name || "—"}</td><td class="mono">${e.target_col || "—"}</td>
            <td>${e.model_name || "—"}</td><td>${e.status}</td><td>${_mlVerdictBadge(m.verdict) || ms}</td>
            <td><button class="btn btn-sm" data-open-exp="${e.id}">Open</button></td></tr>`;
        }).join("")}</tbody></table></div>`;
      $$("#mlExpList [data-open-exp]").forEach((b) => {
        b.onclick = () => openExperiment(Number(b.dataset.openExp));
      });
    } catch (e) {
      $("#mlExpList").textContent = e.message;
    }
  };

  const fillImprovePlan = () => {
    const t = _mlState.last_train || {};
    const m = t.metrics || {};
    const imp = t.feature_importance || [];
    const weak = imp.slice(-Math.max(1, Math.floor(imp.length * 0.3))).map((x) => x.feature);
    const verdict = m.verdict || "—";
    let html = `<p>وضعیت فعلی: ${_mlVerdictBadge(verdict)}</p><ul>`;
    if (String(verdict).indexOf("ضعیف") >= 0 || String(verdict).indexOf("متوسط") >= 0) {
      html += `<li>حذف ویژگی‌های کم‌اهمیت: <code>${weak.slice(0, 8).join(", ") || "—"}</code></li>`;
      html += `<li>آموزش مجدد با همان مدل / GridSearch</li>`;
      html += `<li>در صورت نیاز تعویض مدل به GradientBoosting یا XGBoost</li>`;
    } else {
      html += `<li>مدل فعلاً خوب است. می‌توانی همین را نگه داری یا با مدل دیگر مقایسه کنی.</li>`;
    }
    html += `</ul>`;
    $("#mlImprovePlan").innerHTML = html;
  };

  const renderTrainResult = (r) => {
    _mlState.last_train = r;
    const m = r.metrics || {};
    let kpi = `<div style="margin-bottom:8px">${_mlVerdictBadge(m.verdict)}</div><div class="grid-kpi">`;
    Object.keys(m).forEach((k) => {
      if (k === "verdict") return;
      const v = m[k];
      if (v == null) return;
      kpi += `<div class="kpi cyan"><div class="label">${k}</div><div class="value" style="font-size:1.05rem">${typeof v === "number" ? v.toFixed(4) : v}</div></div>`;
    });
    kpi += `</div>`;
    kpi += `<p class="muted">train=${r.n_train} · test=${r.n_test} · features=${r.n_features}</p>`;
    if (r.best_params && Object.keys(r.best_params).length) {
      kpi += `<p class="muted">best params: <code>${JSON.stringify(r.best_params)}</code></p>`;
    }
    $("#mlMetrics").innerHTML = kpi;
    $("#mlAnalysis").innerHTML = simpleMarkdown(r.analysis || "");
    const imp = r.feature_importance || [];
    if (imp.length) {
      setTimeout(() => {
        safePlot("mlImpChart", [{
          type: "bar",
          orientation: "h",
          y: imp.slice(0, 12).map((x) => x.feature).reverse(),
          x: imp.slice(0, 12).map((x) => x.importance).reverse(),
          marker: { color: "#8b5cf6" },
        }], {
          title: { text: "Feature Importance", font: { color: "#94a3b8", size: 14 } },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { color: "#94a3b8" },
          margin: { t: 40, b: 40, l: 120, r: 20 },
        });
      }, 80);
    }
    fillImprovePlan();
  };

  // Step 1 -> 2
  $("#mlGo2").onclick = () => {
    const sel = $("#mlTable");
    if (!sel.value) { toast("جدول را انتخاب کن", true); return; }
    _mlState.table = sel.value;
    _mlState.table_id = Number(sel.selectedOptions[0].dataset.id) || null;
    goStep(2);
  };

  // Analyze
  $("#mlRunAnalyze").onclick = async () => {
    if (!_mlState.table) { toast("اول جدول را انتخاب کن", true); return; }
    $("#mlAnalyzeStatus").innerHTML = `<div class="empty">در حال تحلیل…</div>`;
    $("#mlAiText").innerHTML = "";
    $("#mlSuggestTargets").innerHTML = "";
    $("#mlGo3").disabled = true;
    try {
      const r = await api("/api/ml/analyze", {
        method: "POST",
        body: JSON.stringify({
          table_name: _mlState.table,
          table_id: _mlState.table_id,
          sample_limit: 3000,
        }),
      });
      if (!r.ok) { toast(r.error || "خطا", true); return; }
      _mlState.profile = r;
      $("#mlAnalyzeStatus").innerHTML = `<span class="badge healthy">تحلیل انجام شد</span> · ${r.n_rows_sampled} ردیف · ${r.n_cols} ستون`;
      $("#mlAiText").innerHTML = simpleMarkdown(r.ai_analysis || "");
      const ts = r.target_suggestions || [];
      let cards = `<h4>پیشنهاد Target</h4>`;
      ts.forEach((t, i) => {
        cards += `<div class="ml-card-select ${i === 0 ? "selected" : ""}" data-target="${t.column}" data-task="${t.task}">
          <b>${t.column}</b> <span class="muted">(${t.task})</span>
          <div class="muted" style="font-size:.78rem">${(t.reasons || []).join(" · ")}</div>
        </div>`;
      });
      $("#mlSuggestTargets").innerHTML = cards;
      $$("#mlSuggestTargets .ml-card-select").forEach((c) => {
        c.onclick = () => {
          $$("#mlSuggestTargets .ml-card-select").forEach((x) => x.classList.remove("selected"));
          c.classList.add("selected");
          _mlState.target = c.dataset.target;
          _mlState.task = c.dataset.task;
        };
      });
      if (ts[0]) {
        _mlState.target = ts[0].column;
        _mlState.task = ts[0].task;
      }
      $("#mlGo3").disabled = false;
      toast("تحلیل آماده است");
    } catch (e) {
      $("#mlAnalyzeStatus").innerHTML = `<span style="color:#f87171">${e.message}</span>`;
    }
  };

  $("#mlGo3").onclick = () => {
    if (!_mlState.profile) return;
    // fill prepare form
    const cols = _mlState.profile.columns || [];
    $("#mlTarget").innerHTML = cols.map((c) =>
      `<option value="${c.name}">${c.name}${c.business_name ? " — " + c.business_name : ""}</option>`
    ).join("");
    if (_mlState.target) $("#mlTarget").value = _mlState.target;
    if (_mlState.task) $("#mlTask").value = _mlState.task;
    $("#mlPrepList").innerHTML = "<b>اقدامات پیش‌پردازش:</b><ul>" +
      (_mlState.profile.preprocess_suggestions || []).map((s) =>
        `<li><code>${s.action}</code> — ${s.reason || ""} ${s.columns ? " [" + (s.columns || []).slice(0, 8).join(", ") + "]" : ""}</li>`
      ).join("") + "</ul>";
    goStep(3);
  };

  // Prepare
  $("#mlPrepare").onclick = async () => {
    _mlState.target = $("#mlTarget").value;
    _mlState.task = $("#mlTask").value;
    $("#mlPrepOut").innerHTML = `<div class="empty">ساخت dataset تمیز…</div>`;
    $("#mlGo4").disabled = true;
    try {
      const drops = [];
      (_mlState.profile.preprocess_suggestions || []).forEach((s) => {
        if (s.action === "drop_columns" && s.columns) drops.push(...s.columns);
      });
      const r = await api("/api/ml/prepare", {
        method: "POST",
        body: JSON.stringify({
          table_name: _mlState.table,
          target_col: _mlState.target,
          drop_cols: drops,
          create_sql_view: true,
          sample_limit: 10000,
        }),
      });
      if (!r.ok) {
        $("#mlPrepOut").innerHTML = `<p style="color:#f87171">${r.error}</p>`;
        return;
      }
      _mlState.dataset_path = r.dataset_path;
      _mlState.experiment_id = r.experiment_id;
      $("#mlPrepOut").innerHTML = simpleMarkdown(
        `✅ آماده‌سازی انجام شد\n\n- ردیف: **${r.n_rows}** · ویژگی: **${r.n_features}**\n` +
        `- فایل: \`${r.dataset_path}\`\n` +
        (r.view_name ? `- VIEW: \`${r.view_name}\`\n` : "") +
        `\n_${r.note || ""}_`
      );
      $("#mlGo4").disabled = false;
      toast("Prepare OK");
    } catch (e) {
      $("#mlPrepOut").innerHTML = `<p style="color:#f87171">${e.message}</p>`;
    }
  };

  $("#mlGo4").onclick = () => {
    // model cards from profile
    const ms = (_mlState.profile && _mlState.profile.model_suggestions) || {};
    const models = ms.models || [
      { name: "RandomForest", why: "قوی و پایدار" },
      { name: "GradientBoosting", why: "دقت بالا" },
      { name: "XGBoost", why: "اغلب بهترین روی tabular" },
    ];
    let html = "";
    models.forEach((m, i) => {
      const short = (m.name || "").replace(/Classifier|Regressor/g, "");
      html += `<div class="ml-card-select ${i === 0 ? "selected" : ""}" data-model="${short}">
        <b>${short}</b><div class="muted" style="font-size:.78rem">${m.why || ""}</div>
      </div>`;
    });
    $("#mlModelCards").innerHTML = html;
    $$("#mlModelCards .ml-card-select").forEach((c) => {
      c.onclick = () => {
        $$("#mlModelCards .ml-card-select").forEach((x) => x.classList.remove("selected"));
        c.classList.add("selected");
        _mlState.model = c.dataset.model;
        $("#mlModel").value = c.dataset.model;
      };
    });
    if (models[0]) {
      const short = (models[0].name || "RandomForest").replace(/Classifier|Regressor/g, "");
      _mlState.model = short;
      $("#mlModel").value = short;
    }
    goStep(4);
  };

  // Train
  $("#mlGo5").onclick = async () => {
    _mlState.model = $("#mlModel").value;
    if (!_mlState.dataset_path) { toast("اول Prepare کن", true); return; }
    goStep(5);
    $("#mlTrainStatus").innerHTML = `<div class="empty">آموزش + GridSearch در حال اجرا…</div>`;
    $("#mlMetrics").innerHTML = "";
    $("#mlAnalysis").innerHTML = "";
    try {
      const r = await api("/api/ml/train", {
        method: "POST",
        body: JSON.stringify({
          dataset_path: _mlState.dataset_path,
          target_col: _mlState.target,
          model_name: _mlState.model,
          task_type: _mlState.task,
          grid_search: true,
          experiment_id: _mlState.experiment_id,
        }),
      });
      $("#mlTrainStatus").innerHTML = "";
      if (!r.ok) {
        $("#mlMetrics").innerHTML = `<p style="color:#f87171">${r.error || "خطا"}</p>`;
        return;
      }
      renderTrainResult(r);
      refreshExp();
      toast("آموزش تمام شد");
    } catch (e) {
      $("#mlTrainStatus").innerHTML = "";
      $("#mlMetrics").innerHTML = `<p style="color:#f87171">${e.message}</p>`;
    }
  };

  $("#mlGo6").onclick = () => {
    fillImprovePlan();
    refreshExp();
    goStep(6);
  };

  const renderFinal = () => {
    const t = _mlState.last_train || {};
    const m = t.metrics || {};
    const path = t.model_path || "—";
    $("#mlFinalSummary").innerHTML = simpleMarkdown(
      `## مدل پذیرفته‌شده\n\n` +
      `- جدول: **${_mlState.table || "—"}**\n` +
      `- Target: **${_mlState.target || t.target_col || "—"}**\n` +
      `- نوع: **${t.task_type || _mlState.task || "—"}**\n` +
      `- مدل: **${t.model_name || _mlState.model || "—"}**\n` +
      `- ویژگی‌ها: **${t.n_features || "—"}** · train/test: **${t.n_train || "—"}** / **${t.n_test || "—"}**\n` +
      `- فایل مدل: \`${path}\`\n` +
      `- وضعیت: ${_mlVerdictBadge(m.verdict)}`
    );
    let kpi = `<div class="grid-kpi">`;
    Object.keys(m).forEach((k) => {
      if (k === "verdict" || m[k] == null) return;
      const v = m[k];
      kpi += `<div class="kpi cyan"><div class="label">${k}</div><div class="value" style="font-size:1.05rem">${typeof v === "number" ? v.toFixed(4) : v}</div></div>`;
    });
    kpi += `</div>`;
    if (t.best_params && Object.keys(t.best_params).length) {
      kpi += `<p class="muted" style="margin-top:8px">best params: <code>${JSON.stringify(t.best_params)}</code></p>`;
    }
    if (t.features && t.features.length) {
      kpi += `<p class="muted">features: <code>${t.features.join(", ")}</code></p>`;
    }
    $("#mlFinalMetrics").innerHTML = kpi;
    $("#mlFinalAnalysis").innerHTML = simpleMarkdown(t.analysis || "");

    const imp = t.feature_importance || [];
    setTimeout(() => {
      if (imp.length) {
        safePlot("mlFinalImpChart", [{
          type: "bar", orientation: "h",
          y: imp.slice(0, 12).map((x) => x.feature).reverse(),
          x: imp.slice(0, 12).map((x) => x.importance).reverse(),
          marker: { color: "#8b5cf6" },
        }], {
          title: { text: "Importance", font: { color: "#94a3b8", size: 13 } },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: "#94a3b8" }, margin: { t: 36, b: 36, l: 110, r: 16 },
        });
      }
      const pr = t.predictions || {};
      const yt = pr.y_true || [];
      const yp = pr.y_pred || [];
      if (yt.length && yp.length) {
        const isClass = (t.task_type || "") === "classification";
        if (isClass) {
          // simple index scatter
          safePlot("mlFinalPredChart", [
            { type: "scatter", mode: "markers", name: "Actual", x: yt.map((_, i) => i + 1), y: yt, marker: { color: "#06b6d4", size: 7 } },
            { type: "scatter", mode: "markers", name: "Pred", x: yp.map((_, i) => i + 1), y: yp, marker: { color: "#8b5cf6", size: 7 } },
          ], {
            title: { text: "Actual vs Pred", font: { color: "#94a3b8", size: 13 } },
            paper_bgcolor: "transparent", plot_bgcolor: "transparent",
            font: { color: "#94a3b8" }, margin: { t: 36, b: 40, l: 48, r: 16 },
            legend: { orientation: "h" },
          });
        } else {
          safePlot("mlFinalPredChart", [
            {
              type: "scatter", mode: "markers", name: "points",
              x: yt, y: yp,
              marker: { color: "#8b5cf6", size: 8, opacity: 0.85 },
            },
            {
              type: "scatter", mode: "lines", name: "ideal",
              x: [Math.min(...yt.map(Number)), Math.max(...yt.map(Number))],
              y: [Math.min(...yt.map(Number)), Math.max(...yt.map(Number))],
              line: { color: "#22c55e", dash: "dot", width: 2 },
            },
          ], {
            title: { text: "Predicted vs Actual", font: { color: "#94a3b8", size: 13 } },
            paper_bgcolor: "transparent", plot_bgcolor: "transparent",
            font: { color: "#94a3b8" }, margin: { t: 36, b: 48, l: 56, r: 16 },
            xaxis: { title: "Actual" }, yaxis: { title: "Predicted" },
            legend: { orientation: "h" },
          });
        }
      } else {
        const elp = document.getElementById("mlFinalPredChart");
        if (elp) elp.innerHTML = `<p class="muted" style="padding:24px">داده پیش‌بینی برای نمودار موجود نیست — یک‌بار دیگر Train کن.</p>`;
      }
    }, 100);
    // predict panel helpers
    const feats = t.features || [];
    const sample = {};
    feats.forEach((f) => { sample[f] = 0; });
    const ta = $("#mlPredictJson");
    if (ta && !ta.value.trim()) ta.value = JSON.stringify([sample], null, 2);
    if ($("#mlPredictMeta")) {
      $("#mlPredictMeta").textContent = `experiment_id=${_mlState.experiment_id || "—"} · features: ${feats.join(", ") || "—"} · model: ${t.model_path || "—"}`;
    }
    if ($("#mlPredictSnippet") && t.model_path) {
      $("#mlPredictSnippet").style.display = "block";
      $("#mlPredictSnippet").textContent =
        "import joblib\n" +
        "bundle = joblib.load(r'" + t.model_path + "')\n" +
        "model = bundle['model']\n" +
        "features = bundle['features']\n" +
        "# X = df[features]  ;  preds = model.predict(X)";
    }
  };

  $("#mlFinalize").onclick = () => {
    if (!_mlState.last_train) { toast("ابتدا مدل را آموزش بده", true); return; }
    renderFinal();
    goStep(7);
    toast("مدل نهایی ثبت شد");
  };
  if ($("#mlRestart2")) $("#mlRestart2").onclick = () => $("#mlRestart").click();

  const _mlRunPredict = async (useDataset) => {
    if (!_mlState.experiment_id) {
      toast("experiment_id نیست — مدل را Finalize کن", true);
      return;
    }
    let body = { experiment_id: _mlState.experiment_id };
    if (useDataset) {
      if (!_mlState.dataset_path && !(_mlState.last_train || {}).dataset_path) {
        toast("dataset_path موجود نیست", true);
        return;
      }
      body.dataset_path = _mlState.dataset_path || _mlState.last_train.dataset_path;
    } else {
      let records;
      try {
        records = JSON.parse(($("#mlPredictJson").value || "[]").trim() || "[]");
      } catch (e) {
        toast("JSON نامعتبر", true);
        return;
      }
      if (!Array.isArray(records) || !records.length) {
        toast("حداقل یک ردیف JSON بده", true);
        return;
      }
      body.records = records;
    }
    $("#mlPredictMetrics").innerHTML = `<div class="muted">در حال پیش‌بینی…</div>`;
    try {
      const r = await api("/api/ml/predict", { method: "POST", body: JSON.stringify(body) });
      if (!r.ok) {
        $("#mlPredictMetrics").innerHTML = `<p style="color:#f87171">${r.error || "خطا"}</p>`;
        return;
      }
      let kpi = `<div class="grid-kpi">`;
      kpi += `<div class="kpi"><div class="label">rows</div><div class="value" style="font-size:1.1rem">${r.n_rows || 0}</div></div>`;
      const m = r.metrics || {};
      Object.keys(m).forEach((k) => {
        const v = m[k];
        kpi += `<div class="kpi cyan"><div class="label">${k}</div><div class="value" style="font-size:1.05rem">${typeof v === "number" ? v.toFixed(4) : v}</div></div>`;
      });
      kpi += `</div>`;
      $("#mlPredictMetrics").innerHTML = kpi;
      if (r.load_snippet && $("#mlPredictSnippet")) {
        $("#mlPredictSnippet").style.display = "block";
        $("#mlPredictSnippet").textContent = r.load_snippet;
      }
      const rows = r.rows || [];
      if (rows.length) {
        const cols = Object.keys(rows[0]);
        let html = `<table class="bi-data-table"><thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>`;
        rows.slice(0, 50).forEach((row) => {
          html += `<tr>${cols.map(c => `<td>${row[c] ?? ""}</td>`).join("")}</tr>`;
        });
        html += `</tbody></table>`;
        $("#mlPredictTable").innerHTML = html;
      }
      const preds = (r.predictions || []).map(Number).filter((x) => !Number.isNaN(x));
      if (preds.length && typeof safePlot === "function") {
        safePlot("mlPredictChart", [{
          type: "scatter", mode: "lines+markers",
          x: preds.map((_, i) => i + 1), y: preds,
          line: { color: "#8b5cf6", width: 3 },
          marker: { color: "#06b6d4", size: 7 },
          name: "prediction",
        }], {
          title: { text: "Predictions", font: { color: "#94a3b8", size: 13 } },
          paper_bgcolor: "transparent", plot_bgcolor: "transparent",
          font: { color: "#94a3b8" }, margin: { t: 36, b: 40, l: 48, r: 16 },
        });
      }
      toast("پیش‌بینی انجام شد");
    } catch (e) {
      $("#mlPredictMetrics").innerHTML = `<p style="color:#f87171">${e.message}</p>`;
    }
  };
  document.addEventListener("click", (ev) => {
    if (ev.target && ev.target.id === "mlPredictRun") _mlRunPredict(false);
    if (ev.target && ev.target.id === "mlPredictDataset") _mlRunPredict(true);
    if (ev.target && ev.target.id === "mlCopyLoadCode") {
      const sn = ($("#mlPredictSnippet") && $("#mlPredictSnippet").textContent) || "";
      if (!sn) { toast("کدی نیست", true); return; }
      navigator.clipboard.writeText(sn).then(() => toast("کد کپی شد — در Notebook پیست کن")).catch(() => toast(sn));
    }
  });

  // Improve + retrain
  $("#mlApplyImprove").onclick = async () => {
    if (!_mlState.last_train || !_mlState.dataset_path) {
      toast("ابتدا یک مدل آموزش بده", true);
      return;
    }
    $("#mlImproveOut").innerHTML = `<div class="empty">اعمال بهبود و آموزش مجدد…</div>`;
    try {
      const r = await api("/api/ml/improve", {
        method: "POST",
        body: JSON.stringify({
          dataset_path: _mlState.dataset_path,
          target_col: _mlState.target,
          model_name: _mlState.model,
          task_type: _mlState.task,
          experiment_id: _mlState.experiment_id,
          drop_weak_features: true,
          weak_fraction: 0.3,
          previous_importance: (_mlState.last_train.feature_importance || []),
        }),
      });
      if (!r.ok) {
        $("#mlImproveOut").innerHTML = `<p style="color:#f87171">${r.error}</p>`;
        return;
      }
      if (r.dataset_path) _mlState.dataset_path = r.dataset_path;
      if (r.experiment_id) _mlState.experiment_id = r.experiment_id;
      $("#mlImproveOut").innerHTML = simpleMarkdown(
        `بهبود اعمال شد. ویژگی‌های حذف‌شده: \`${(r.dropped_features || []).join(", ") || "—"}\`\n\n` +
        (r.analysis ? r.analysis : "")
      );
      renderTrainResult(r);
      // also show metrics briefly in improve panel
      refreshExp();
      toast("آموزش مجدد انجام شد");
      // jump to results to show charts clearly
      goStep(5);
    } catch (e) {
      $("#mlImproveOut").innerHTML = `<p style="color:#f87171">${e.message}</p>`;
    }
  };

  $("#mlRestart").onclick = () => {
    _mlState = { step: 1, table: null, table_id: null, profile: null, target: null, task: null, model: "RandomForest", dataset_path: null, experiment_id: null, last_train: null, history: [] };
    goStep(1);
  };

  const sendChat = async () => {
    const msg = ($("#mlChatInput").value || "").trim();
    if (!msg) return;
    $("#mlChatInput").value = "";
    addChat("user", msg.replace(/</g, "&lt;"));
    try {
      const r = await api("/api/ml/chat", {
        method: "POST",
        body: JSON.stringify({ message: msg, context: _mlCtx() }),
      });
      addChat("bot", simpleMarkdown(r.answer || "—"));
    } catch (e) {
      addChat("bot", e.message);
    }
  };
  $("#mlChatSend").onclick = sendChat;
  $("#mlChatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });


  const openExperiment = async (id) => {
    try {
      const r = await api("/api/ml/experiments/" + id);
      if (!r.ok) { toast(r.error || "یافت نشد", true); return; }
      const e = r.experiment;
      _mlState.table = e.table_name || _mlState.table;
      _mlState.target = e.target_col;
      _mlState.task = e.task_type;
      _mlState.model = e.model_name;
      _mlState.dataset_path = e.dataset_path;
      _mlState.experiment_id = e.id;
      _mlState.last_train = {
        ok: true,
        experiment_id: e.id,
        task_type: e.task_type,
        model_name: e.model_name,
        metrics: e.metrics || {},
        best_params: e.best_params || {},
        feature_importance: [],
        model_path: e.model_path,
        n_train: null,
        n_test: null,
        n_features: e.n_features,
        analysis: e.analysis || "",
        predictions: e.predictions || {},
        target_col: e.target_col,
        features: e.features || [],
        dataset_path: e.dataset_path,
      };
      // switch to wizard final
      setMlMode("wizard");
      renderFinal();
      goStep(7);
      toast("مدل از تاریخچه باز شد");
    } catch (err) {
      toast(err.message, true);
    }
  };

  const setMlMode = (mode) => {
    $("#mlModeWizardView").style.display = mode === "wizard" ? "" : "none";
    $("#mlModeHistoryView").style.display = mode === "history" ? "" : "none";
    $("#mlModeProView").style.display = mode === "pro" ? "" : "none";
    $$("[data-mlmode]").forEach((b) => {
      b.classList.toggle("primary", b.dataset.mlmode === mode);
    });
    if (mode === "history") renderHistFull();
    if (mode === "pro") nbShowLibrary();
  };
  $$("[data-mlmode]").forEach((b) => {
    b.onclick = () => setMlMode(b.dataset.mlmode);
  });

  const renderHistFull = async () => {
    try {
      const r = await api("/api/ml/experiments?limit=50");
      const list = r.experiments || [];
      if (!list.length) {
        $("#mlHistFull").innerHTML = `<div class="muted">هنوز مدلی ذخیره نشده. از Wizard یکی بساز.</div>`;
        return;
      }
      $("#mlHistFull").innerHTML = `<div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>زمان</th><th>جدول</th><th>Target</th><th>Model</th><th>Status</th><th>نتیجه</th><th></th></tr></thead>
        <tbody>${list.map((e) => {
          const m = e.metrics || {};
          return `<tr>
            <td>${e.id}</td><td class="muted">${e.created_at || "—"}</td>
            <td class="mono">${e.table_name || "—"}</td>
            <td class="mono">${e.target_col || "—"}</td>
            <td>${e.model_name || "—"}</td><td>${e.status}</td>
            <td>${_mlVerdictBadge(m.verdict) || "—"}</td>
            <td><button class="btn btn-sm primary" data-open-exp="${e.id}">باز کردن</button></td>
          </tr>`;
        }).join("")}</tbody></table></div>`;
      $$("#mlHistFull [data-open-exp]").forEach((b) => {
        b.onclick = () => openExperiment(Number(b.dataset.openExp));
      });
    } catch (e) {
      $("#mlHistFull").textContent = e.message;
    }
  };
  $("#mlHistRefresh").onclick = renderHistFull;

  /* ---- PRO Notebook ---- */

  const pyHighlight = (src) => {
    if (!src) return " ";
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    // tokenize roughly
    const kw = "and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield".split(" ");
    const bi = "False True None self cls print len range list dict set tuple str int float bool type open enumerate zip map filter sum min max abs round sorted any all".split(" ");
    const kwSet = new Set(kw);
    const biSet = new Set(bi);
    let out = "";
    let i = 0;
    const s = src;
    while (i < s.length) {
      // comments
      if (s[i] === "#") {
        let j = i;
        while (j < s.length && s[j] !== "\\n") j++;
        out += `<span class="tok-cmt">${esc(s.slice(i, j))}</span>`;
        i = j;
        continue;
      }
      // strings
      if (s[i] === "'" || s[i] === '"') {
        const q = s[i];
        let j = i + 1;
        // triple
        if (s.slice(i, i + 3) === q + q + q) {
          j = i + 3;
          while (j < s.length && s.slice(j, j + 3) !== q + q + q) j++;
          j = Math.min(s.length, j + 3);
          out += `<span class="tok-str">${esc(s.slice(i, j))}</span>`;
          i = j;
          continue;
        }
        while (j < s.length && s[j] !== q) {
          if (s[j] === "\\\\") j += 2;
          else j++;
        }
        j = Math.min(s.length, j + 1);
        out += `<span class="tok-str">${esc(s.slice(i, j))}</span>`;
        i = j;
        continue;
      }
      // numbers
      if (/[0-9]/.test(s[i]) && (i === 0 || /[^\w]/.test(s[i - 1]))) {
        let j = i;
        while (j < s.length && /[0-9._]/.test(s[j])) j++;
        out += `<span class="tok-num">${esc(s.slice(i, j))}</span>`;
        i = j;
        continue;
      }
      // identifiers
      if (/[A-Za-z_]/.test(s[i])) {
        let j = i;
        while (j < s.length && /[\w]/.test(s[j])) j++;
        const word = s.slice(i, j);
        // function name if followed by (
        let k = j;
        while (k < s.length && s[k] === " ") k++;
        if (s[k] === "(" && !kwSet.has(word)) {
          out += `<span class="tok-fn">${esc(word)}</span>`;
        } else if (kwSet.has(word)) {
          out += `<span class="tok-kw">${esc(word)}</span>`;
        } else if (biSet.has(word)) {
          out += `<span class="tok-builtin">${esc(word)}</span>`;
        } else if (word.startsWith("__")) {
          out += `<span class="tok-deco">${esc(word)}</span>`;
        } else {
          out += esc(word);
        }
        i = j;
        continue;
      }
      // decorator
      if (s[i] === "@") {
        let j = i + 1;
        while (j < s.length && /[\w.]/.test(s[j])) j++;
        out += `<span class="tok-deco">${esc(s.slice(i, j))}</span>`;
        i = j;
        continue;
      }
      out += esc(s[i]);
      i++;
    }
    return out || " ";
  };

  const syncNbHighlight = (cellEl) => {
    const ta = cellEl.querySelector(".nb-code");
    const pre = cellEl.querySelector(".nb-highlight");
    if (!ta || !pre) return;
    pre.innerHTML = pyHighlight(ta.value);
    // resize textarea height to content
    ta.style.height = "auto";
    const h = Math.max(96, ta.scrollHeight);
    ta.style.height = h + "px";
    cellEl.querySelector(".nb-code-wrap").style.height = h + "px";
  };


  let nbSession = null;
  let nbNotebookId = null;
  let nbNotebookName = "";
  let nbCellSeq = 0;

  const nbRenderResult = (cellEl, res) => {
    const out = cellEl.querySelector(".nb-out");
    if (!res.ok) {
      out.innerHTML = `<div class="nb-out-label">ERROR</div><pre class="nb-err">${(res.error || res.stderr || "error").replace(/</g, "&lt;")}</pre>`;
      return;
    }
    let html = `<div class="nb-out-label">OUTPUT</div>`;
    if (res.stdout) html += `<pre class="nb-stdout">${String(res.stdout).replace(/</g, "&lt;")}</pre>`;
    if (res.stderr) html += `<pre class="nb-stderr">${String(res.stderr).replace(/</g, "&lt;")}</pre>`;
    const r = res.result;
    if (r) {
      if (r.type === "image" && r.image_base64) {
        html += `<img class="nb-img" src="data:image/png;base64,${r.image_base64}" alt="plot" />`;
      } else if (r.type === "dataframe" && r.html) {
        html += `<div class="nb-df-wrap">${r.html}<div class="muted">shape: ${(r.shape || []).join("×")}</div></div>`;
      } else if (r.text) {
        html += `<pre class="nb-stdout">${String(r.text).replace(/</g, "&lt;")}</pre>`;
      }
    }
    if (html === `<div class="nb-out-label">OUTPUT</div>`) html += `<span class="muted">Done</span>`;
    out.innerHTML = html;
  };

  const nbAddCell = (code, afterEl) => {
    nbCellSeq += 1;
    const id = "c" + nbCellSeq;
    const div = document.createElement("div");
    div.className = "nb-cell";
    div.dir = "ltr";
    div.dataset.cellId = id;
    div.innerHTML = `
      <div class="nb-cell-bar">
        <span class="muted">In [${nbCellSeq}]</span>
        <span class="muted" style="font-size:.68rem">Shift+Enter Run · Alt+Enter New</span>
        <div class="row-actions">
          <button class="btn btn-sm primary nb-run">Run</button>
          <button class="btn btn-sm nb-del">✕</button>
        </div>
      </div>
      <div class="nb-code-wrap" dir="ltr">
        <pre class="nb-highlight" dir="ltr"></pre>
        <textarea class="nb-code" dir="ltr" spellcheck="false" placeholder="# Python…">${code || ""}</textarea>
      </div>
      <div class="nb-out"></div>`;
    if (afterEl && afterEl.parentNode) {
      afterEl.parentNode.insertBefore(div, afterEl.nextSibling);
    } else {
      $("#nbCells").appendChild(div);
    }
    const ta = div.querySelector(".nb-code");
    const runCell = async () => {
      if (!nbSession) { toast("اول Kernel را Start کن", true); return; }
      const codeVal = ta.value;
      div.querySelector(".nb-out").innerHTML = `<div class="nb-out-label">OUTPUT</div><div class="empty">Running…</div>`;
      try {
        const r = await api("/api/ml/notebook/exec", {
          method: "POST",
          body: JSON.stringify({ session_id: nbSession, code: codeVal, cell_id: id }),
        });
        nbRenderResult(div, r);
      } catch (e) {
        div.querySelector(".nb-out").innerHTML = `<div class="nb-out-label">ERROR</div><pre class="nb-err">${e.message}</pre>`;
      }
    };
    div.querySelector(".nb-run").onclick = runCell;
    div.querySelector(".nb-del").onclick = () => div.remove();
    ta.addEventListener("input", () => syncNbHighlight(div));
    ta.addEventListener("scroll", () => {
      div.querySelector(".nb-highlight").scrollTop = ta.scrollTop;
      div.querySelector(".nb-highlight").scrollLeft = ta.scrollLeft;
    });
    ta.addEventListener("keydown", (e) => {
      // Shift+Enter → run
      if (e.key === "Enter" && e.shiftKey && !e.altKey) {
        e.preventDefault();
        runCell();
        return;
      }
      // Alt+Enter → new cell below
      if (e.key === "Enter" && e.altKey) {
        e.preventDefault();
        const n = nbAddCell("", div);
        n.querySelector(".nb-code").focus();
        return;
      }
      // Tab insert spaces
      if (e.key === "Tab") {
        e.preventDefault();
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        ta.value = ta.value.slice(0, start) + "    " + ta.value.slice(end);
        ta.selectionStart = ta.selectionEnd = start + 4;
        syncNbHighlight(div);
      }
    });
    syncNbHighlight(div);
    return div;
  };


  async function nbShowLibrary() {
    $("#nbLib")?.classList.remove("hidden");
    $("#nbEditor")?.classList.add("hidden");
    const list = $("#nbLibList");
    if (!list) return;
    list.innerHTML = `<div class="muted">بارگذاری…</div>`;
    try {
      const r = await api("/api/ml/notebooks");
      const items = r.items || [];
      if (!items.length) {
        list.innerHTML = `<div class="empty">نوت‌بوکی ذخیره نشده. «نوت‌بوک جدید» را بزن.</div>`;
        return;
      }
      list.innerHTML = `<div class="bi-lib-grid">${items.map((n) => `
        <div class="bi-lib-card">
          <div class="bi-lib-icon">📓</div>
          <div class="bi-lib-body">
            <div class="bi-lib-name">${(n.name || "Notebook").replace(/</g, "")}</div>
            <div class="bi-lib-meta">#${n.id} · ${n.table_name || "no table"} · ${n.updated_at || "—"}</div>
          </div>
          <div class="bi-lib-actions">
            <button type="button" class="btn btn-sm primary" data-nb-open="${n.id}">باز کردن</button>
            <button type="button" class="btn btn-sm" data-nb-del="${n.id}">حذف</button>
          </div>
        </div>`).join("")}</div>`;
      list.querySelectorAll("[data-nb-open]").forEach((b) => {
        b.onclick = () => nbOpenNotebook(Number(b.dataset.nbOpen));
      });
      list.querySelectorAll("[data-nb-del]").forEach((b) => {
        b.onclick = async () => {
          if (!confirm("حذف این نوت‌بوک؟")) return;
          await api("/api/ml/notebooks/" + b.dataset.nbDel, { method: "DELETE" });
          toast("حذف شد");
          nbShowLibrary();
        };
      });
    } catch (e) {
      list.innerHTML = `<div class="empty">${e.message}</div>`;
    }
  }

  function nbCollectCells() {
    return $$("#nbCells .nb-cell").map((div) => ({
      code: (div.querySelector(".nb-code") || {}).value || "",
    }));
  }

  async function nbOpenNotebook(id) {
    try {
      const r = await api("/api/ml/notebooks/" + id);
      if (!r.ok) { toast(r.error || "خطا", true); return; }
      nbNotebookId = r.id;
      nbNotebookName = r.name || "Notebook";
      $("#nbLib")?.classList.add("hidden");
      $("#nbEditor")?.classList.remove("hidden");
      if (r.table_name && $("#nbTable")) {
        $("#nbTable").value = r.table_name;
      }
      $("#nbCells").innerHTML = "";
      const cells = r.cells || [];
      if (!cells.length) nbAddCell("");
      else cells.forEach((c) => nbAddCell(c.code || ""));
      toast("نوت‌بوک باز شد — Start Kernel را بزن");
    } catch (e) {
      toast(e.message, true);
    }
  }

  function nbOpenNew() {
    nbNotebookId = null;
    nbNotebookName = "";
    $("#nbLib")?.classList.add("hidden");
    $("#nbEditor")?.classList.remove("hidden");
    $("#nbCells").innerHTML = "";
    nbSession = null;
    $("#nbStatus").textContent = "kernel خاموش";
    $("#nbReset").disabled = true;
    $("#nbAddCell").disabled = true;
    // one empty cell only after kernel start — leave empty until start
  }

  async function nbSaveNotebook() {
    const cells = nbCollectCells();
    if (!cells.length) {
      toast("سلولی نیست", true);
      return;
    }
    const name = prompt("نام نوت‌بوک:", nbNotebookName || "Notebook");
    if (!name || !name.trim()) return;
    try {
      const r = await api("/api/ml/notebooks", {
        method: "POST",
        body: JSON.stringify({
          ...(nbNotebookId ? { id: nbNotebookId } : {}),
          name: name.trim(),
          table_name: ($("#nbTable") && $("#nbTable").value) || "",
          cells,
        }),
      });
      if (!r.ok) { toast(r.error || "خطا", true); return; }
      nbNotebookId = r.id;
      nbNotebookName = r.name;
      toast("نوت‌بوک ذخیره شد");
    } catch (e) {
      toast(e.message, true);
    }
  }

  $("#nbStart").onclick = async () => {
    const table = $("#nbTable").value || null;
    $("#nbStatus").textContent = "starting…";
    try {
      const r = await api("/api/ml/notebook/session", {
        method: "POST",
        body: JSON.stringify({ table_name: table, sample_limit: 10000 }),
      });
      if (!r.ok) { toast(r.error || "خطا", true); $("#nbStatus").textContent = "error"; return; }
      nbSession = r.session_id;
      $("#nbStatus").textContent = `kernel: ${nbSession}` + (r.csv_path ? ` · df ready` : "");
      $("#nbHints").textContent = (r.hints || []).join(" · ") + (r.note ? " — " + r.note : "");
      $("#nbReset").disabled = false;
      $("#nbAddCell").disabled = false;
      $("#nbCells").innerHTML = "";
      nbAddCell(table
        ? "df.head()\\n# df.shape, df.describe(), df.columns"
        : "import pandas as pd\\n# df = pd.read_csv(CSV_PATH) after loading a table");
      toast("Kernel آماده است");
    } catch (e) {
      $("#nbStatus").textContent = e.message;
    }
  };
  $("#nbReset").onclick = async () => {
    if (!nbSession) return;
    await api("/api/ml/notebook/reset", { method: "POST", body: JSON.stringify({ session_id: nbSession }) });
    toast("Kernel ریست شد");
  };
  $("#nbAddCell").onclick = () => nbAddCell("");
  if ($("#nbNewNotebook")) $("#nbNewNotebook").onclick = () => nbOpenNew();
  if ($("#nbBackLib")) $("#nbBackLib").onclick = () => nbShowLibrary();
  if ($("#nbSaveNotebook")) $("#nbSaveNotebook").onclick = () => nbSaveNotebook();

  refreshExp();
  goStep(1);
}




/* ---------- Pipeline / Warehouse Studio (pro) ---------- */
let _pl = null;
let _plDrag = null;      // { id, ox, oy }
let _plLink = null;      // { fromId, x1, y1 }
let _plRaf = null;

const PL_NODE_W = 180;
const PL_NODE_H = 78;

async function loadPipeline() {
  const el = $("#content");
  el.innerHTML = `<div class="empty">بارگذاری…</div>`;
  _pl = {
    id: null, name: "", warehouse: {}, nodes: [], edges: [],
    schedule: { enabled: false, cron: "0 2 * * *", timezone: "Asia/Tehran" },
    load_mode: "full", status: "draft",
    selectedNode: null, lake: [],
  };
  _plDrag = null;
  _plLink = null;

  el.innerHTML = `
  <div class="pl-studio" id="plStudio">
    <div class="pl-lib" id="plLib">
      <div class="bi-hero">
        <div>
          <h3 style="margin:0">انبار داده و پایپ‌لاین</h3>
          <p class="muted" style="margin:6px 0 0">یک Warehouse بساز یا DAG ذخیره‌شده را باز کن</p>
        </div>
        <button class="btn primary" id="plNewWh">＋ New Warehouse</button>
      </div>
      <div id="plLibList" class="bi-lib-list"><div class="muted">…</div></div>
    </div>

    <div class="pl-wizard hidden" id="plWizard">
      <div class="panel pl-wizard-card">
        <h3 style="margin-top:0">New Warehouse</h3>
        <p class="muted">مقصد بارگذاری داده را مشخص کن</p>
        <div class="pl-form-grid">
          <label class="field"><span>نام</span><input id="plWhName" placeholder="Sales Mart" /></label>
          <label class="field"><span>Host</span><input id="plWhHost" placeholder="127.0.0.1" dir="ltr" /></label>
          <label class="field"><span>Port</span><input id="plWhPort" value="5432" dir="ltr" /></label>
          <label class="field"><span>Database</span><input id="plWhDb" placeholder="dw_sales" dir="ltr" /></label>
          <label class="field"><span>User</span><input id="plWhUser" placeholder="postgres" dir="ltr" /></label>
          <label class="field"><span>Password</span><input id="plWhPass" type="password" dir="ltr" /></label>
          <label class="field"><span>Schema</span><input id="plWhSchema" value="mart" dir="ltr" /></label>
          <label class="field"><span>Default load</span>
            <select id="plWhMode"><option value="full">Full refresh</option><option value="upsert">Upsert</option></select>
          </label>
        </div>
        <div class="row-actions" style="margin-top:14px">
          <button class="btn" id="plWhCancel">انصراف</button>
          <button class="btn primary" id="plWhCreate">ایجاد و باز کردن میزکار</button>
        </div>
        <div id="plWhMsg" class="muted" style="margin-top:8px"></div>
      </div>
    </div>

    <div class="pl-bench hidden" id="plBench" dir="ltr">
      <header class="pl-bar">
        <button type="button" class="pl-bar-btn" id="plBackLib">← Library</button>
        <div class="pl-bar-title">
          <strong id="plNameLabel">Pipeline</strong>
          <span class="pl-pill" id="plStatusBadge">draft</span>
        </div>
        <div class="pl-bar-actions">
          <button type="button" class="pl-bar-btn ghost" id="plCompile">SQL Preview</button>
          <button type="button" class="pl-bar-btn" id="plRunMat" style="color:#4ade80;border-color:rgba(34,197,94,.4)">▶ Run / Create tables</button>
          <button type="button" class="pl-bar-btn primary" id="plSave">Save</button>
        </div>
      </header>

      <div class="pl-workspace">
        <!-- LEFT: sources from lake -->
        <aside class="pl-panel pl-panel-lake">
          <div class="pl-panel-h">Data Lake</div>
          <input id="plLakeSearch" class="pl-search" placeholder="Filter tables…" />
          <div id="plLakeList" class="pl-scroll"></div>
          <div class="pl-hint">Drag a table onto the canvas</div>
        </aside>

        <!-- CENTER: canvas -->
        <section class="pl-stage">
          <div class="pl-tools">
            <span class="pl-tools-label">Add step</span>
            <button type="button" class="pl-tool" data-pladd="join" title="Join two streams">
              <b>⋈</b><span>Join</span>
            </button>
            <button type="button" class="pl-tool" data-pladd="transform" title="Clean / transform">
              <b>✦</b><span>Transform</span>
            </button>
            <button type="button" class="pl-tool" data-pladd="output" title="Write to warehouse">
              <b>▣</b><span>Output</span>
            </button>
            <button type="button" class="pl-tool" data-pladd="comment" title="Sticky note">
              <b>✎</b><span>Note</span>
            </button>
            <span class="pl-tools-sep"></span>
            <span class="pl-tools-hint" id="plHint">Drag tables → connect → double-click preview → Save → Run</span>
          </div>
          <div class="pl-viewport" id="plViewport">
            <svg class="pl-svg" id="plSvg"></svg>
            <div class="pl-layer" id="plLayer"></div>
            <div class="pl-empty" id="plEmpty">
              <div class="pl-empty-ill">◎</div>
              <h3>Build your data flow</h3>
              <ol>
                <li>Drag tables from <b>Data Lake</b></li>
                <li>Add <b>Join</b> / <b>Transform</b> / <b>Output</b></li>
                <li>Drag from <span class="pl-port-demo out"></span> to <span class="pl-port-demo in"></span> to connect</li>
                <li>Click a node to configure it</li>
              </ol>
            </div>
          </div>
        </section>

        <!-- RIGHT: inspector -->
        <aside class="pl-panel pl-panel-insp" dir="rtl">
          <div class="pl-panel-h">Properties</div>
          <div id="plInsp" class="pl-scroll pl-insp"></div>
          <div class="pl-sched-box" dir="rtl">
            <div class="pl-panel-h" style="border:0;padding:0 0 8px">اجرا و زمان‌بندی</div>
            <label class="field"><span>Load mode</span>
              <select id="plLoadMode"><option value="full">Full refresh</option><option value="upsert">Upsert</option></select>
            </label>
            <label class="pl-check"><input type="checkbox" id="plSchedEn" /> فعال‌سازی Schedule</label>
            <label class="field"><span>Cron</span><input id="plCron" value="0 2 * * *" dir="ltr" /></label>
            <label class="field"><span>Timezone</span><input id="plTz" value="Asia/Tehran" dir="ltr" /></label>
          </div>
        </aside>
      </div>

      <div class="pl-sql-drawer hidden" id="plSqlDrawer">
        <div class="pl-sql-h">Compiled SQL <button type="button" class="pl-bar-btn" id="plSqlClose">Close</button></div>
        <pre id="plSqlOut" class="mono"></pre>
      </div>
      <div class="pl-modal hidden" id="plModal">
        <div class="pl-modal-card">
          <div class="pl-modal-h">
            <strong id="plModalTitle">Preview</strong>
            <button type="button" class="pl-bar-btn" id="plModalClose">✕</button>
          </div>
          <div id="plModalMeta" class="muted" style="padding:0 14px 8px;font-size:.75rem"></div>
          <div id="plModalBody" class="pl-modal-body"></div>
        </div>
      </div>
    </div>
    <div class="pl-props hidden" id="plProps"></div>
  </div>`;

  // wire once
  $("#plNewWh").onclick = () => {
    $("#plLib").classList.add("hidden");
    $("#plWizard").classList.remove("hidden");
    $("#plBench").classList.add("hidden");
  };
  $("#plWhCancel").onclick = () => plShowLib();
  $("#plWhCreate").onclick = () => plCreateWarehouse();
  $("#plBackLib").onclick = () => plShowLib();
  $("#plSave").onclick = () => plSave();
  $("#plCompile").onclick = () => plCompile();
  $("#plRunMat").onclick = () => plMaterialize();
  $("#plSqlClose").onclick = () => $("#plSqlDrawer").classList.add("hidden");
  $("#plModalClose").onclick = () => $("#plModal").classList.add("hidden");
  $("#plLakeSearch").oninput = () => plRenderLake($("#plLakeSearch").value);
  $("#plLoadMode").onchange = () => { _pl.load_mode = $("#plLoadMode").value; };
  $("#plSchedEn").onchange = () => { _pl.schedule.enabled = $("#plSchedEn").checked; };
  $("#plCron").onchange = () => { _pl.schedule.cron = $("#plCron").value; };
  $("#plTz").onchange = () => { _pl.schedule.timezone = $("#plTz").value; };

  $$("[data-pladd]").forEach((b) => {
    b.onclick = () => plAddNode(b.dataset.pladd);
  });

  // global pointer handlers (one time per load)
  document.addEventListener("mousemove", plOnMove);
  document.addEventListener("mouseup", plOnUp);

  const layer = $("#plLayer");
  layer.addEventListener("dragover", (e) => e.preventDefault());
  layer.addEventListener("drop", async (e) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("text/pl-table");
    if (!raw) return;
    let info; try { info = JSON.parse(raw); } catch { return; }
    const vp = $("#plViewport").getBoundingClientRect();
    const x = e.clientX - vp.left + $("#plViewport").scrollLeft - PL_NODE_W / 2;
    const y = e.clientY - vp.top + $("#plViewport").scrollTop - 20;
    await plAddSource(info, Math.max(24, x), Math.max(24, y));
  });

  plShowLib();
}

function plHint(msg) {
  const el = $("#plHint");
  if (el) el.textContent = msg;
}

async function plShowLib() {
  $("#plLib").classList.remove("hidden");
  $("#plWizard").classList.add("hidden");
  $("#plBench").classList.add("hidden");
  $("#plProps")?.classList.add("hidden");
  const list = $("#plLibList");
  list.innerHTML = `<div class="muted">Loading…</div>`;
  try {
    const r = await api("/api/pipeline/list");
    const items = r.items || [];
    if (!items.length) {
      list.innerHTML = `<div class="empty">No warehouse yet — create one with <b>New Warehouse</b>.</div>`;
      return;
    }
    list.innerHTML = `<div class="pl-lib-grid">${items.map((p) => `
      <div class="pl-wh-card">
        <div class="pl-wh-top">
          <div class="pl-wh-icon">⬡</div>
          <div class="pl-wh-info">
            <div class="pl-wh-name">${esc(p.name)}</div>
            <div class="pl-wh-meta">#${p.id} · ${esc(p.warehouse_db || p.host || "—")} · ${p.nodes || 0} nodes · ${esc(p.load_mode || "full")}</div>
          </div>
        </div>
        <div class="pl-wh-actions">
          <button type="button" class="btn btn-sm primary" data-o="${p.id}">Open</button>
          <button type="button" class="btn btn-sm" data-p="${p.id}">Properties</button>
          <button type="button" class="btn btn-sm" data-d="${p.id}">Delete</button>
        </div>
      </div>`).join("")}</div>`;
    list.querySelectorAll("[data-o]").forEach((b) => b.onclick = () => plOpen(+b.dataset.o));
    list.querySelectorAll("[data-p]").forEach((b) => b.onclick = () => plShowProperties(+b.dataset.p));
    list.querySelectorAll("[data-d]").forEach((b) => b.onclick = async () => {
      if (!confirm("Delete this pipeline?")) return;
      await api("/api/pipeline/" + b.dataset.d, { method: "DELETE" });
      plShowLib();
    });
  } catch (e) {
    list.innerHTML = `<div class="empty">${e.message}</div>`;
  }
}

function esc(s) {
  return String(s || "").replace(/</g, "&lt;");
}

async function plCreateWarehouse() {
  const body = {
    name: $("#plWhName").value || "Warehouse",
    host: $("#plWhHost").value,
    port: Number($("#plWhPort").value || 5432),
    database: $("#plWhDb").value,
    user: $("#plWhUser").value,
    password: $("#plWhPass").value,
    schema: $("#plWhSchema").value || "mart",
    load_mode: $("#plWhMode").value,
  };
  $("#plWhMsg").textContent = "Creating…";
  try {
    const r = await api("/api/pipeline/warehouse", { method: "POST", body: JSON.stringify(body) });
    if (!r.ok) { $("#plWhMsg").textContent = r.error || "Error"; return; }
    toast(r.note || "Created");
    await plOpen(r.pipeline_id);
  } catch (e) {
    $("#plWhMsg").textContent = e.message;
  }
}

async function plOpen(pid) {
  const r = await api("/api/pipeline/" + pid);
  if (!r.ok) { toast(r.error || "Not found", true); return; }
  const p = r.pipeline;
  Object.assign(_pl, {
    id: p.id, name: p.name, warehouse: p.warehouse || {},
    nodes: p.nodes || [], edges: p.edges || [],
    schedule: p.schedule || _pl.schedule,
    load_mode: p.load_mode || "full", status: p.status || "draft",
    selectedNode: null,
  });
  $("#plLib").classList.add("hidden");
  $("#plWizard").classList.add("hidden");
  $("#plBench").classList.remove("hidden");
  $("#plNameLabel").textContent = _pl.name;
  $("#plStatusBadge").textContent = _pl.status;
  $("#plLoadMode").value = _pl.load_mode;
  $("#plSchedEn").checked = !!_pl.schedule.enabled;
  $("#plCron").value = _pl.schedule.cron || "0 2 * * *";
  $("#plTz").value = _pl.schedule.timezone || "Asia/Tehran";
  await plLoadLake();
  plPaint();
  plInspect(null);
}

async function plLoadLake() {
  try {
    const r = await api("/api/pipeline/lake-tables");
    _pl.lake = r.tables || [];
  } catch { _pl.lake = []; }
  plRenderLake();
}

function plRenderLake(filter) {
  const q = (filter || "").toLowerCase();
  const list = $("#plLakeList");
  const items = (_pl.lake || []).filter((t) => !q || `${t.schema}.${t.table}`.toLowerCase().includes(q));
  if (!items.length) {
    list.innerHTML = `<div class="muted tiny" style="padding:8px">No tables — run Auto Discovery first</div>`;
    return;
  }
  list.innerHTML = items.map((t) => `
    <div class="pl-tbl" draggable="true" data-schema="${esc(t.schema)}" data-table="${esc(t.table)}">
      <span class="pl-tbl-dot"></span>
      <div>
        <div class="pl-tbl-name">${esc(t.table)}</div>
        <div class="pl-tbl-sch">${esc(t.schema)}</div>
      </div>
    </div>`).join("");
  list.querySelectorAll(".pl-tbl").forEach((el) => {
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/pl-table", JSON.stringify({
        schema: el.dataset.schema, table: el.dataset.table,
      }));
      e.dataTransfer.effectAllowed = "copy";
    });
  });
}

function plUid(p) { return p + "_" + Math.random().toString(36).slice(2, 8); }

async function plAddSource(info, x, y) {
  let columns = [];
  try {
    const r = await api(`/api/pipeline/columns?schema=${encodeURIComponent(info.schema)}&table=${encodeURIComponent(info.table)}`);
    columns = (r.columns || []).map((c) => c.name);
  } catch {}
  const node = {
    id: plUid("src"), type: "source",
    schema: info.schema, table: info.table,
    columns, selected_columns: columns.slice(0, Math.min(8, columns.length)) || columns.slice(),
    x, y,
  };
  _pl.nodes.push(node);
  plPaint();
  plSelect(node.id);
  plHint("Source added — connect its output port to Join or Transform");
}

function plAddNode(type) {
  const n = {
    id: plUid(type.slice(0, 3)), type,
    x: 280 + _pl.nodes.length * 28,
    y: 100 + (_pl.nodes.length % 5) * 36,
  };
  if (type === "join") {
    n.join_type = "inner";
    n.on = [{ left_col: "", right_col: "" }];
  } else if (type === "transform") {
    n.ops = ["dedupe"];
    n.note = "";
  } else if (type === "output") {
    n.target_table = "mart_output";
    n.load_mode = _pl.load_mode || "full";
    n.upsert_keys = [];
  } else if (type === "comment") {
    n.text = "یادداشت…";
    n.color = ["amber", "pink", "cyan", "green", "violet"][_pl.nodes.length % 5];
    n.w = 200;
    n.h = 100;
  }
  _pl.nodes.push(n);
  plPaint();
  plSelect(n.id);
  plHint(type === "join"
    ? "Connect two sources into this Join, then set join keys"
    : type === "output"
      ? "Connect the final step into Output and set target table"
      : "Connect a stream into Transform and pick cleanup ops");
}

function plSelect(id) {
  _pl.selectedNode = id;
  // only toggle selected class
  $$(".pl-nd").forEach((el) => el.classList.toggle("on", el.dataset.id === id));
  const node = _pl.nodes.find((n) => n.id === id);
  plInspect(node || null);
}

function plPaint() {
  const layer = $("#plLayer");
  const empty = $("#plEmpty");
  if (!layer) return;
  empty.style.display = _pl.nodes.length ? "none" : "flex";

  // rebuild nodes only (edges via SVG)
  layer.innerHTML = "";
  _pl.nodes.forEach((n) => {
    const el = document.createElement("div");
    el.dataset.id = n.id;
    el.style.transform = `translate(${n.x || 0}px, ${n.y || 0}px)`;

    if (n.type === "comment") {
      el.className = "pl-note pl-note-" + (n.color || "amber") + (n.id === _pl.selectedNode ? " on" : "");
      el.style.width = (n.w || 200) + "px";
      el.innerHTML = `
        <div class="pl-note-bar">Note</div>
        <textarea class="pl-note-text" placeholder="Comment…">${esc(n.text || "")}</textarea>
        <button type="button" class="pl-note-x" title="Remove">×</button>`;
      const ta = el.querySelector(".pl-note-text");
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      ta.addEventListener("input", () => { n.text = ta.value; });
      el.querySelector(".pl-note-x").onclick = (e) => {
        e.stopPropagation();
        _pl.nodes = _pl.nodes.filter((x) => x.id !== n.id);
        plPaint();
        plInspect(null);
      };
      el.addEventListener("mousedown", (e) => {
        if (e.target.closest("textarea") || e.target.closest(".pl-note-x")) return;
        plSelect(n.id);
        _plDrag = { id: n.id, ox: e.clientX - (n.x || 0), oy: e.clientY - (n.y || 0) };
        e.preventDefault();
      });
      layer.appendChild(el);
      return;
    }

    el.className = "pl-nd pl-nd-" + n.type + (n.id === _pl.selectedNode ? " on" : "");
    const title = n.type === "source" ? (n.table || "table")
      : n.type === "join" ? "Join"
      : n.type === "transform" ? "Transform"
      : (n.target_table || "Output");
    const meta = n.type === "source" ? (n.schema || "public")
      : n.type === "join" ? ((n.join_type || "inner") + " join")
      : n.type === "transform" ? ((n.ops || []).join(" · ") || "ops")
      : (n.load_mode || "full");
    el.innerHTML = `
      <div class="pl-nd-hd"><span class="pl-nd-kind">${n.type}</span></div>
      <div class="pl-nd-title">${esc(title)}</div>
      <div class="pl-nd-meta">${esc(meta)}</div>
      <button type="button" class="pl-port pl-port-in" data-port="in" title="Input"></button>
      <button type="button" class="pl-port pl-port-out" data-port="out" title="Output — drag to connect"></button>
    `;
    el.addEventListener("mousedown", (e) => {
      if (e.target.closest(".pl-port")) return;
      plSelect(n.id);
      _plDrag = { id: n.id, ox: e.clientX - (n.x || 0), oy: e.clientY - (n.y || 0) };
      e.preventDefault();
    });
    el.addEventListener("dblclick", (e) => {
      if (e.target.closest(".pl-port")) return;
      e.preventDefault();
      plPreviewNode(n.id);
    });
    el.querySelector(".pl-port-out").addEventListener("mousedown", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const c = plPortCenter(n.id, "out");
      _plLink = { fromId: n.id, x1: c.x, y1: c.y, x2: c.x, y2: c.y };
      plHint("Drop on an input port to connect");
      plDrawEdges();
    });
    el.querySelector(".pl-port-in").addEventListener("mouseup", (e) => {
      e.stopPropagation();
      if (_plLink && _plLink.fromId !== n.id) {
        const fr = _plLink.fromId;
        if (!_pl.edges.some((ed) => ed.from === fr && ed.to === n.id)) {
          _pl.edges.push({ from: fr, to: n.id });
        }
        _plLink = null;
        plDrawEdges();
        plHint("Connected");
        plSelect(n.id);
      }
    });
    layer.appendChild(el);
  });
  plDrawEdges();
}

function plPortCenter(nodeId, which) {
  const n = _pl.nodes.find((x) => x.id === nodeId);
  if (!n) return { x: 0, y: 0 };
  const x = (n.x || 0) + (which === "out" ? PL_NODE_W : 0);
  const y = (n.y || 0) + PL_NODE_H / 2;
  return { x, y };
}

function plDrawEdges() {
  const svg = $("#plSvg");
  const vp = $("#plViewport");
  if (!svg || !vp) return;
  const W = Math.max(vp.scrollWidth, vp.clientWidth, 1200);
  const H = Math.max(vp.scrollHeight, vp.clientHeight, 700);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  let html = `<defs>
    <linearGradient id="plG" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#a78bfa"/>
    </linearGradient>
  </defs>`;

  _pl.edges.forEach((e) => {
    const a = plPortCenter(e.from, "out");
    const b = plPortCenter(e.to, "in");
    const dx = Math.max(40, Math.abs(b.x - a.x) * 0.45);
    const d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
    html += `<path class="pl-wire" d="${d}" />`;
    html += `<circle class="pl-pulse" r="3.5"><animateMotion dur="2s" repeatCount="indefinite" path="${d}"/></circle>`;
  });

  if (_plLink) {
    const a = { x: _plLink.x1, y: _plLink.y1 };
    const b = { x: _plLink.x2, y: _plLink.y2 };
    const dx = Math.max(30, Math.abs(b.x - a.x) * 0.4);
    const d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
    html += `<path class="pl-wire pl-wire-temp" d="${d}" />`;
  }

  svg.innerHTML = html;
}

function plOnMove(e) {
  if (_plDrag) {
    const n = _pl.nodes.find((x) => x.id === _plDrag.id);
    if (!n) return;
    n.x = Math.max(0, e.clientX - _plDrag.ox);
    n.y = Math.max(0, e.clientY - _plDrag.oy);
    const el = document.querySelector(`.pl-nd[data-id="${n.id}"]`);
    if (el) el.style.transform = `translate(${n.x}px, ${n.y}px)`;
    if (!_plRaf) {
      _plRaf = requestAnimationFrame(() => {
        _plRaf = null;
        plDrawEdges();
      });
    }
    return;
  }
  if (_plLink) {
    const vp = $("#plViewport");
    if (!vp) return;
    const r = vp.getBoundingClientRect();
    _plLink.x2 = e.clientX - r.left + vp.scrollLeft;
    _plLink.y2 = e.clientY - r.top + vp.scrollTop;
    if (!_plRaf) {
      _plRaf = requestAnimationFrame(() => {
        _plRaf = null;
        plDrawEdges();
      });
    }
  }
}

function plOnUp(e) {
  if (_plLink) {
    // if released on input port, handled by port mouseup; else cancel
    const t = e.target;
    if (!t || !t.classList || !t.classList.contains("pl-port-in")) {
      _plLink = null;
      plDrawEdges();
      plHint("Connection cancelled");
    }
  }
  _plDrag = null;
}

function plInspect(node) {
  const box = $("#plInsp");
  if (!box) return;
  if (!node) {
    const wh = _pl.warehouse || {};
    box.innerHTML = `
      <div class="pl-card">
        <div class="pl-card-t">Warehouse</div>
        <div class="pl-card-v">${esc(wh.name || _pl.name)}</div>
        <div class="pl-mono">${esc(wh.host || "—")}:${wh.port || ""} / ${esc(wh.database || "")}</div>
        <div class="muted" style="margin-top:6px">schema: <b>${esc(wh.schema || "mart")}</b></div>
        <div class="muted" style="margin-top:8px">${_pl.nodes.length} nodes · ${_pl.edges.length} links</div>
        <p class="muted" style="margin-top:12px;font-size:.78rem;line-height:1.5">
          برای شروع یک جدول از Data Lake بکش روی بوم، بعد Join یا Output اضافه کن و پورت‌ها را وصل کن.
        </p>
      </div>`;
    return;
  }

  if (node.type === "source") {
    const cols = node.columns || [];
    const sel = new Set(node.selected_columns || []);
    box.innerHTML = `
      <div class="pl-card">
        <div class="pl-card-t">Source table</div>
        <div class="pl-card-v">${esc(node.table)}</div>
        <div class="pl-mono">${esc(node.schema)}.${esc(node.table)}</div>
        <div class="pl-sec">Columns in pipeline</div>
        <div class="pl-col-list">${cols.map((c) => `
          <label class="pl-check"><input type="checkbox" data-c="${esc(c)}" ${sel.has(c)?"checked":""}/> ${esc(c)}</label>`).join("") || "—"}</div>
        <button type="button" class="btn btn-sm danger" id="plRm" style="margin-top:12px">Remove node</button>
      </div>`;
    box.querySelectorAll("[data-c]").forEach((chk) => {
      chk.onchange = () => {
        node.selected_columns = [...box.querySelectorAll("[data-c]:checked")].map((x) => x.dataset.c);
      };
    });
  } else if (node.type === "join") {
    const ins = _pl.edges.filter((e) => e.to === node.id).map((e) => _pl.nodes.find((n) => n.id === e.from)).filter(Boolean);
    const left = ins[0], right = ins[1];
    const lcols = (left && left.columns) || [];
    const rcols = (right && right.columns) || [];
    const on0 = (node.on && node.on[0]) || {};
    box.innerHTML = `
      <div class="pl-card">
        <div class="pl-card-t">Join</div>
        <p class="muted" style="font-size:.8rem;line-height:1.45;margin:6px 0 10px">
          دو جریان ورودی را وصل کن، بعد کلیدهای برابر را انتخاب کن.
        </p>
        <div class="pl-join-map">
          <div class="pl-join-side">
            <div class="muted tiny">LEFT</div>
            <div class="pl-card-v" style="font-size:.9rem">${left ? esc(left.table) : "— connect source"}</div>
          </div>
          <div class="pl-join-x">⋈</div>
          <div class="pl-join-side">
            <div class="muted tiny">RIGHT</div>
            <div class="pl-card-v" style="font-size:.9rem">${right ? esc(right.table) : "— connect source"}</div>
          </div>
        </div>
        <label class="field"><span>Join type</span>
          <select id="plJT"><option value="inner">Inner</option><option value="left">Left</option><option value="right">Right</option><option value="full">Full</option></select>
        </label>
        <label class="field"><span>Left key</span>
          <select id="plJL"><option value="">—</option>${lcols.map((c)=>`<option value="${esc(c)}">${esc(c)}</option>`).join("")}</select>
        </label>
        <label class="field"><span>Right key</span>
          <select id="plJR"><option value="">—</option>${rcols.map((c)=>`<option value="${esc(c)}">${esc(c)}</option>`).join("")}</select>
        </label>
        <button type="button" class="btn btn-sm danger" id="plRm" style="margin-top:12px">Remove node</button>
      </div>`;
    const jt = $("#plJT"), jl = $("#plJL"), jr = $("#plJR");
    if (jt) { jt.value = node.join_type || "inner"; jt.onchange = () => { node.join_type = jt.value; plPaintSoft(node); }; }
    if (jl) { jl.value = on0.left_col || ""; jl.onchange = () => { node.on = [{ left_col: jl.value, right_col: jr.value }]; }; }
    if (jr) { jr.value = on0.right_col || ""; jr.onchange = () => { node.on = [{ left_col: jl.value, right_col: jr.value }]; }; }
  } else if (node.type === "transform") {
    const ops = new Set(node.ops || []);
    box.innerHTML = `
      <div class="pl-card">
        <div class="pl-card-t">Transform</div>
        <p class="muted" style="font-size:.8rem">پردازش روی جریان ورودی</p>
        <label class="pl-check"><input type="checkbox" id="op1" ${ops.has("dedupe")?"checked":""}/> Remove duplicates</label>
        <label class="pl-check"><input type="checkbox" id="op2" ${ops.has("drop_null")?"checked":""}/> Drop null rows</label>
        <label class="pl-check"><input type="checkbox" id="op3" ${ops.has("cast")?"checked":""}/> Normalize types</label>
        <label class="field"><span>Notes</span><textarea id="plNote" rows="2">${esc(node.note||"")}</textarea></label>
        <button type="button" class="btn btn-sm danger" id="plRm" style="margin-top:12px">Remove node</button>
      </div>`;
    const sync = () => {
      const o = [];
      if ($("#op1").checked) o.push("dedupe");
      if ($("#op2").checked) o.push("drop_null");
      if ($("#op3").checked) o.push("cast");
      node.ops = o;
      node.note = $("#plNote").value;
      plPaintSoft(node);
    };
    ["op1","op2","op3","plNote"].forEach((id) => { const el = document.getElementById(id); if (el) el.onchange = sync; });
  } else if (node.type === "output") {
    box.innerHTML = `
      <div class="pl-card">
        <div class="pl-card-t">Warehouse output</div>
        <label class="field"><span>Target table</span><input id="plOT" dir="ltr" value="${esc(node.target_table||"")}" /></label>
        <label class="field"><span>Load mode</span>
          <select id="plOM"><option value="full">Full refresh</option><option value="upsert">Upsert</option></select>
        </label>
        <label class="field"><span>Upsert keys (comma)</span><input id="plOK" dir="ltr" value="${esc((node.upsert_keys||[]).join(", "))}" /></label>
        <button type="button" class="btn btn-sm danger" id="plRm" style="margin-top:12px">Remove node</button>
      </div>`;
    $("#plOM").value = node.load_mode || "full";
    $("#plOT").onchange = () => { node.target_table = $("#plOT").value; plPaintSoft(node); };
    $("#plOM").onchange = () => { node.load_mode = $("#plOM").value; plPaintSoft(node); };
    $("#plOK").onchange = () => { node.upsert_keys = $("#plOK").value.split(",").map((s)=>s.trim()).filter(Boolean); };
  }

  const rm = document.getElementById("plRm");
  if (rm) {
    rm.onclick = () => {
      _pl.nodes = _pl.nodes.filter((n) => n.id !== node.id);
      _pl.edges = _pl.edges.filter((e) => e.from !== node.id && e.to !== node.id);
      _pl.selectedNode = null;
      plPaint();
      plInspect(null);
    };
  }
}

function plPaintSoft(node) {
  // update label only
  const el = document.querySelector(`.pl-nd[data-id="${node.id}"]`);
  if (!el) return;
  const meta = el.querySelector(".pl-nd-meta");
  const title = el.querySelector(".pl-nd-title");
  if (node.type === "join" && meta) meta.textContent = (node.join_type || "inner") + " join";
  if (node.type === "transform" && meta) meta.textContent = (node.ops || []).join(" · ") || "ops";
  if (node.type === "output") {
    if (title) title.textContent = node.target_table || "Output";
    if (meta) meta.textContent = node.load_mode || "full";
  }
}

async function plSave() {
  _pl.load_mode = $("#plLoadMode").value;
  _pl.schedule = { enabled: $("#plSchedEn").checked, cron: $("#plCron").value, timezone: $("#plTz").value };
  const name = prompt("Pipeline name:", _pl.name || "Pipeline");
  if (!name) return;
  const body = {
    ...(_pl.id ? { id: _pl.id } : {}),
    name: name.trim(),
    warehouse: _pl.warehouse,
    nodes: _pl.nodes,
    edges: _pl.edges,
    schedule: _pl.schedule,
    load_mode: _pl.load_mode,
    status: _pl.status || "draft",
  };
  try {
    const r = await api("/api/pipeline/save", { method: "POST", body: JSON.stringify(body) });
    if (!r.ok) { toast(r.error || "Save failed", true); return; }
    _pl.id = r.id;
    _pl.name = r.pipeline?.name || name;
    $("#plNameLabel").textContent = _pl.name;
    toast("Saved #" + r.id);
  } catch (e) { toast(e.message, true); }
}

async function plCompile() {
  try {
    const r = await api("/api/pipeline/compile", {
      method: "POST",
      body: JSON.stringify({
        warehouse: _pl.warehouse, nodes: _pl.nodes, edges: _pl.edges,
        schedule: _pl.schedule, load_mode: _pl.load_mode,
      }),
    });
    $("#plSqlDrawer").classList.remove("hidden");
    $("#plSqlOut").textContent = r.sql || "—";
  } catch (e) { toast(e.message, true); }
}



async function plMaterialize() {
  if (!_pl.id) {
    toast("اول Save کن", true);
    return;
  }
  // auto-save graph first
  try {
    await api("/api/pipeline/save", {
      method: "POST",
      body: JSON.stringify({
        id: _pl.id,
        name: _pl.name,
        warehouse: _pl.warehouse,
        nodes: _pl.nodes,
        edges: _pl.edges,
        schedule: _pl.schedule,
        load_mode: _pl.load_mode,
        status: _pl.status,
      }),
    });
  } catch {}
  toast("در حال ساخت جداول در warehouse…");
  try {
    const r = await api("/api/pipeline/" + _pl.id + "/materialize", { method: "POST", body: "{}" });
    if (!r.ok && !r.materialized) {
      toast(r.error || "Materialize failed", true);
      return;
    }
    const lines = (r.results || []).map((x) =>
      x.ok ? `✓ ${x.output} (${x.rows} rows)` : `✗ ${x.output}: ${x.error}`
    );
    $("#plModal").classList.remove("hidden");
    $("#plModalTitle").textContent = "Materialize result";
    $("#plModalMeta").textContent = `${r.materialized || 0}/${r.total || 0} tables`;
    $("#plModalBody").innerHTML = `<pre class="mono" style="padding:12px;white-space:pre-wrap">${esc(lines.join("\\n") || r.error || "—")}</pre>`;
    toast("Done");
  } catch (e) {
    toast(e.message, true);
  }
}

async function plPreviewNode(nodeId) {
  if (!_pl.id) {
    toast("اول پایپ‌لاین را Save کن تا preview کار کند", true);
    return;
  }
  // save latest graph
  try {
    await api("/api/pipeline/save", {
      method: "POST",
      body: JSON.stringify({
        id: _pl.id, name: _pl.name, warehouse: _pl.warehouse,
        nodes: _pl.nodes, edges: _pl.edges, schedule: _pl.schedule,
        load_mode: _pl.load_mode, status: _pl.status,
      }),
    });
  } catch {}
  $("#plModal").classList.remove("hidden");
  $("#plModalTitle").textContent = "Node preview";
  $("#plModalMeta").textContent = "Loading…";
  $("#plModalBody").innerHTML = `<div class="muted" style="padding:16px">Running query…</div>`;
  try {
    const r = await api("/api/pipeline/" + _pl.id + "/preview", {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId, limit: 50 }),
    });
    if (!r.ok) {
      $("#plModalMeta").textContent = r.error || "Error";
      $("#plModalBody").innerHTML = r.sql ? `<pre class="mono" style="padding:12px">${esc(r.sql)}</pre>` : "";
      return;
    }
    const node = _pl.nodes.find((n) => n.id === nodeId);
    $("#plModalTitle").textContent = (node && (node.table || node.target_table || node.type)) || "Preview";
    $("#plModalMeta").textContent = `${r.row_count || 0} rows · ${r.node_type || ""}`;
    const cols = r.columns || [];
    const rows = r.rows || [];
    if (!cols.length) {
      $("#plModalBody").innerHTML = `<p class="muted" style="padding:16px">No rows</p>`;
      return;
    }
    let html = `<div style="overflow:auto;max-height:420px"><table class="pl-prev-table"><thead><tr>${cols.map((c)=>`<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>`;
    rows.forEach((row) => {
      html += `<tr>${cols.map((c) => `<td>${esc(row[c] ?? "")}</td>`).join("")}</tr>`;
    });
    html += `</tbody></table></div>`;
    if (r.sql) html += `<pre class="mono" style="padding:10px 12px;font-size:.72rem;color:#67e8f9;border-top:1px solid rgba(148,163,184,.1)">${esc(r.sql)}</pre>`;
    $("#plModalBody").innerHTML = html;
  } catch (e) {
    $("#plModalMeta").textContent = e.message;
  }
}

async function plShowProperties(pid) {
  $("#plLib").classList.add("hidden");
  $("#plWizard").classList.add("hidden");
  $("#plBench").classList.add("hidden");
  const box = $("#plProps");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="empty">Loading properties…</div>`;
  try {
    const r = await api("/api/pipeline/" + pid + "/properties");
    if (!r.ok) { box.innerHTML = `<div class="empty">${r.error}</div>`; return; }
    const p = r.pipeline || {};
    const wh = p.warehouse || {};
    const st = r.stats || {};
    const tables = r.table_status || [];
    const runs = r.runs || [];
    box.innerHTML = `
      <div class="pl-prop-page">
        <div class="bi-hero">
          <div>
            <button type="button" class="btn btn-sm" id="plPropBack">← Library</button>
            <h3 style="margin:10px 0 4px">${esc(p.name)}</h3>
            <p class="muted" style="margin:0">Warehouse properties · #${p.id} · status: <b>${esc(p.status || "draft")}</b></p>
          </div>
          <div class="row-actions">
            <button type="button" class="btn" id="plPropOpen">Open canvas</button>
            <button type="button" class="btn primary" id="plPropRun">▶ Materialize tables</button>
          </div>
        </div>
        <div class="pl-prop-grid">
          <div class="panel">
            <div class="panel-head"><h3>Connection</h3></div>
            <label class="field"><span>Name</span><input id="ppName" value="${esc(p.name)}" /></label>
            <label class="field"><span>Description</span><textarea id="ppDesc" rows="2">${esc(p.description || "")}</textarea></label>
            <div class="pl-mono" style="margin:8px 0">${esc(wh.user || "")}@${esc(wh.host || "")}:${wh.port || ""} / ${esc(wh.database || "")}</div>
            <label class="field"><span>Schema</span><input id="ppSchema" dir="ltr" value="${esc(wh.schema || "mart")}" /></label>
            <label class="field"><span>Load mode</span>
              <select id="ppMode"><option value="full">Full</option><option value="upsert">Upsert</option></select>
            </label>
            <label class="pl-check"><input type="checkbox" id="ppSched" ${p.schedule && p.schedule.enabled ? "checked" : ""}/> Schedule enabled</label>
            <label class="field"><span>Cron</span><input id="ppCron" dir="ltr" value="${esc((p.schedule||{}).cron || "0 2 * * *")}" /></label>
            <button type="button" class="btn primary" id="ppSave" style="margin-top:8px">Save properties</button>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>Graph stats</h3></div>
            <div class="grid-kpi">
              <div class="kpi"><div class="label">Sources</div><div class="value" style="font-size:1.2rem">${st.sources||0}</div></div>
              <div class="kpi cyan"><div class="label">Joins</div><div class="value" style="font-size:1.2rem">${st.joins||0}</div></div>
              <div class="kpi amber"><div class="label">Transforms</div><div class="value" style="font-size:1.2rem">${st.transforms||0}</div></div>
              <div class="kpi green"><div class="label">Outputs</div><div class="value" style="font-size:1.2rem">${st.outputs||0}</div></div>
            </div>
            <p class="muted" style="margin-top:10px">Edges: ${st.edges||0} · Notes: ${st.comments||0} · Last run: ${esc(p.last_run_at || "—")}</p>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>Output tables (warehouse)</h3></div>
            <div id="ppTables">${tables.length ? `<table class="pl-prev-table"><thead><tr><th>Table</th><th>Exists</th><th>Rows</th><th>Mode</th></tr></thead><tbody>
              ${tables.map((t) => `<tr><td class="mono">${esc(t.table||t.error||"—")}</td><td>${t.exists?"✓":"—"}</td><td>${t.rows ?? "—"}</td><td>${esc(t.load_mode||"")}</td></tr>`).join("")}
            </tbody></table>` : `<p class="muted">No outputs yet or warehouse unreachable</p>`}</div>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>Run history</h3></div>
            ${(runs||[]).map((run) => `
              <div class="pl-run-item">
                <b>${esc(run.at)}</b> · ${run.ok ? "OK" : "FAIL"}
                <div class="muted tiny">${(run.results||[]).map((x)=>x.ok?x.output:(x.output+": "+x.error)).join(" · ")}</div>
              </div>`).join("") || `<p class="muted">No runs yet — use Materialize</p>`}
          </div>
          <div class="panel" style="grid-column:1/-1">
            <div class="panel-head"><h3>Compiled SQL</h3></div>
            <pre class="mono" style="max-height:220px;overflow:auto;padding:10px;background:#0a0f1c;border-radius:10px;color:#a5f3fc;direction:ltr;text-align:left">${esc(r.sql||"—")}</pre>
          </div>
        </div>
      </div>`;
    const mode = document.getElementById("ppMode");
    if (mode) mode.value = p.load_mode || "full";
    $("#plPropBack").onclick = () => { box.classList.add("hidden"); plShowLib(); };
    $("#plPropOpen").onclick = () => { box.classList.add("hidden"); plOpen(pid); };
    $("#plPropRun").onclick = async () => {
      toast("Materializing…");
      const res = await api("/api/pipeline/" + pid + "/materialize", { method: "POST", body: JSON.stringify({}) });
      toast(res.ok ? `Created ${res.materialized} table(s)` : (res.error || "Failed"), !res.ok);
      plShowProperties(pid);
    };
    $("#ppSave").onclick = async () => {
      const body = {
        id: pid,
        name: $("#ppName").value,
        description: $("#ppDesc").value,
        warehouse: { ...wh, schema: $("#ppSchema").value },
        nodes: p.nodes || [],
        edges: p.edges || [],
        load_mode: $("#ppMode").value,
        schedule: { enabled: $("#ppSched").checked, cron: $("#ppCron").value, timezone: (p.schedule||{}).timezone || "Asia/Tehran" },
        status: p.status || "draft",
        runs: p.runs || [],
      };
      const res = await api("/api/pipeline/save", { method: "POST", body: JSON.stringify(body) });
      toast(res.ok ? "Saved" : (res.error || "Error"), !res.ok);
    };
  } catch (e) {
    box.innerHTML = `<div class="empty">${e.message}</div>`;
  }
}

