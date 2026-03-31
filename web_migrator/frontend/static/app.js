// app.js — AppSheet → PostgreSQL Web Migrator

const state = {
  sessionId: null,
  appName: null,
  tables: [],
  currentJobId: null,
  currentEventSource: null,
};

// ---------------------------------------------------------------------------
// Step navigation
// ---------------------------------------------------------------------------
function showStep(stepId) {
  document.querySelectorAll(".step").forEach((el) => el.classList.add("hidden"));
  document.getElementById(stepId).classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------------------
// Loading overlay
// ---------------------------------------------------------------------------
function showOverlay(msg) {
  document.getElementById("overlay-msg").textContent = msg;
  document.getElementById("log-lines").innerHTML = "";
  document.getElementById("loading-overlay").classList.remove("hidden");
}

function hideOverlay() {
  document.getElementById("loading-overlay").classList.add("hidden");
  if (state.currentEventSource) {
    state.currentEventSource.close();
    state.currentEventSource = null;
  }
}

function appendLog(line) {
  const container = document.getElementById("log-lines");
  const el = document.createElement("div");
  el.textContent = line;
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

// ---------------------------------------------------------------------------
// Step 1 — Upload
// ---------------------------------------------------------------------------
document.getElementById("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const appName = document.getElementById("app-name").value.trim();
  const files = document.getElementById("csv-files").files;

  if (!appName) return alert(t("error.app_required"));
  if (!files.length) return alert(t("error.files_required"));

  const formData = new FormData();
  formData.append("app_name", appName);
  for (const file of files) formData.append("files", file);

  setLoading("upload-btn", true);
  showOverlay(t("overlay.uploading", { n: files.length }));
  // No stop button for upload (it's fast)
  document.getElementById("overlay-stop-btn").classList.add("hidden");

  try {
    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      showError("upload-error", Array.isArray(data.detail) ? data.detail.join("\n") : data.detail);
      return;
    }

    state.sessionId = data.session_id;
    state.appName   = data.app_name;
    state.tables    = data.tables;

    if (data.errors?.length) {
      showError("upload-error", t("error.files_had_errors") + data.errors.join("\n"));
    } else {
      hideError("upload-error");
    }

    renderValidation(data.tables);
    showStep("step-validate");
  } catch (err) {
    showError("upload-error", t("error.network") + err.message);
  } finally {
    setLoading("upload-btn", false);
    hideOverlay();
  }
});

// ---------------------------------------------------------------------------
// Step 2 — Validation
// ---------------------------------------------------------------------------
function renderValidation(tables) {
  const container = document.getElementById("validation-cards");
  container.innerHTML = "";

  tables.forEach((table) => {
    const hasWarnings =
      table.warnings.length > 0 || table.columns.some((c) => c.warnings.length > 0);

    const warningBadge = hasWarnings
      ? `<span class="badge badge-warn">${t("validate.badge.warnings")}</span>`
      : `<span class="badge badge-ok">${t("validate.badge.clean")}</span>`;

    const columnRows = table.columns
      .map((col) => {
        const colWarn = col.warnings.length
          ? `<span class="col-warn">⚠ ${col.warnings.join("; ")}</span>`
          : "";
        return `
          <tr>
            <td class="col-name">${esc(col.name)}</td>
            <td><code>${col.pg_type}</code></td>
            <td>${col.empty_count > 0 ? `${col.empty_count} (${(col.empty_ratio * 100).toFixed(0)}%)` : "—"}</td>
            <td>${colWarn}</td>
          </tr>`;
      })
      .join("");

    const tableWarnings = table.warnings.length
      ? `<div class="table-warnings">${table.warnings.map((w) => `⚠ ${esc(w)}`).join("<br>")}</div>`
      : "";

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-header">
        <div>
          <span class="table-title">${esc(table.table_name)}</span>
          <span class="table-meta">${table.row_count} rows · ${table.column_count} columns</span>
        </div>
        ${warningBadge}
      </div>
      ${tableWarnings}
      <div class="table-scroll">
        <table class="col-table">
          <thead><tr><th>${t("validate.col.column")}</th><th>${t("validate.col.type")}</th><th>${t("validate.col.empty")}</th><th>${t("validate.col.warnings")}</th></tr></thead>
          <tbody>${columnRows}</tbody>
        </table>
      </div>
      <button class="btn btn-sm btn-secondary" onclick="openPreview('${esc(table.table_name)}')">
        ${t("validate.preview_btn")}
      </button>
    `;
    container.appendChild(card);
  });
}

document.getElementById("confirm-btn").addEventListener("click", () => {
  renderConfirmation(state.tables);
  showStep("step-confirm");
});

document.getElementById("back-to-upload").addEventListener("click", () => showStep("step-upload"));

// ---------------------------------------------------------------------------
// Preview modal
// ---------------------------------------------------------------------------
function openPreview(tableName) {
  const table = state.tables.find((t) => t.table_name === tableName);
  if (!table) return;

  document.getElementById("preview-title").textContent = `${t("preview.title")}: ${tableName}`;
  const cols = table.columns.map((c) => c.name);
  const rows = table.preview;

  const thead = cols.map((c) => `<th>${esc(c)}</th>`).join("");
  const tbody = rows.map((row) =>
    `<tr>${cols.map((c) => `<td>${row[c] != null ? esc(String(row[c])) : '<span class="null">NULL</span>'}</td>`).join("")}</tr>`
  ).join("");

  document.getElementById("preview-table-container").innerHTML = `
    <div class="table-scroll">
      <table class="preview-table">
        <thead><tr>${thead}</tr></thead>
        <tbody>${tbody}</tbody>
      </table>
    </div>`;

  document.getElementById("preview-info").textContent =
    `${t("preview.showing")} ${rows.length} ${t("preview.of")}`;
  document.getElementById("preview-modal").classList.remove("hidden");
}

document.getElementById("close-preview").addEventListener("click", () => {
  document.getElementById("preview-modal").classList.add("hidden");
});

// ---------------------------------------------------------------------------
// Step 3 — Confirmation
// ---------------------------------------------------------------------------
function renderConfirmation(tables) {
  const tbody = tables
    .map((tbl) => `
      <tr>
        <td>${esc(tbl.table_name)}</td>
        <td>${tbl.row_count}</td>
        <td>${tbl.column_count}</td>
        <td>${tbl.warnings.length ? `<span class="warn-text">⚠ ${tbl.warnings.length} ${t("warn.warnings")}</span>` : "—"}</td>
      </tr>`)
    .join("");

  document.getElementById("confirm-table-body").innerHTML = tbody;
  document.getElementById("confirm-app-name").textContent = state.appName;
  document.getElementById("confirm-schema").textContent = `appsheet.${state.appName}_<table>`;
  document.getElementById("confirm-total-rows").textContent = tables.reduce(
    (sum, t) => sum + t.row_count, 0
  );
}

document.getElementById("back-to-validate").addEventListener("click", () => showStep("step-validate"));
document.getElementById("sync-btn").addEventListener("click", () => runSync(false));
document.getElementById("dryrun-btn").addEventListener("click", () => runSync(true));

// ---------------------------------------------------------------------------
// Sync via SSE
// ---------------------------------------------------------------------------
async function runSync(dryRun) {
  setLoading("sync-btn", true);
  setLoading("dryrun-btn", true);
  hideError("sync-error");

  // 1. Start job FIRST — show overlay only after we know it succeeded
  const formData = new FormData();
  formData.append("session_id", state.sessionId);
  formData.append("dry_run", dryRun ? "true" : "false");

  let jobId;
  try {
    const res = await fetch("/sync/start", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      setLoading("sync-btn", false);
      setLoading("dryrun-btn", false);
      if (res.status === 404) {
        showError("sync-error", t("error.session_expired"));
      } else {
        showError("sync-error", data.detail || t("error.sync_failed"));
      }
      return;
    }

    jobId = data.job_id;
    state.currentJobId = jobId;
    state.streamToken = data.stream_token;
  } catch (err) {
    setLoading("sync-btn", false);
    setLoading("dryrun-btn", false);
    showError("sync-error", t("error.network") + err.message);
    return;
  }

  // Job started successfully — now show the overlay with logs
  showOverlay(dryRun ? t("overlay.dryrun") : t("overlay.syncing"));
  document.getElementById("overlay-stop-btn").classList.remove("hidden");

  // 2. Stream logs via SSE
  const es = new EventSource(`/sync/stream/${jobId}?token=${state.streamToken}`);
  state.currentEventSource = es;

  es.onmessage = (e) => {
    appendLog(e.data);
  };

  es.addEventListener("result", (e) => {
    const result = JSON.parse(e.data);
    es.close();
    state.currentEventSource = null;
    hideOverlay();
    setLoading("sync-btn", false);
    setLoading("dryrun-btn", false);
    renderResult(result, dryRun);
    showStep("step-result");
  });

  es.addEventListener("done", () => {
    es.close();
    state.currentEventSource = null;
    hideOverlay();
    setLoading("sync-btn", false);
    setLoading("dryrun-btn", false);
  });

  es.onerror = () => {
    es.close();
    state.currentEventSource = null;
    hideOverlay();
    setLoading("sync-btn", false);
    setLoading("dryrun-btn", false);
    showError("sync-error", t("error.connection_lost"));
  };
}

// Stop button
document.getElementById("overlay-stop-btn").addEventListener("click", async () => {
  if (!state.currentJobId) return;
  document.getElementById("overlay-msg").textContent = t("overlay.stopping");
  document.getElementById("overlay-stop-btn").disabled = true;
  try {
    await fetch(`/sync/stop/${state.currentJobId}`, { method: "POST" });
  } catch (_) {}
});

// ---------------------------------------------------------------------------
// Step 4 — Result
// ---------------------------------------------------------------------------
function renderResult(data, dryRun) {
  document.getElementById("result-title").textContent = dryRun
    ? t("step4.dryrun.title")
    : t("step4.title");

  const rowLabel = dryRun ? t("result.rows_validated") : t("result.rows_inserted");
  document.getElementById("result-summary").innerHTML = `
    <p>${t("result.app")}: <strong>${esc(data.app_name)}</strong></p>
    <p>${t("result.schema")}: <code>appsheet</code> · Tables: <code>appsheet.${esc(data.app_name)}_&lt;table&gt;</code></p>
    <p>${rowLabel}: <strong>${data.total_inserted}</strong></p>
    ${dryRun ? `<p class="dry-run-note">${t("result.dryrun_note")}</p>` : ""}
  `;

  const rows = data.tables
    .map((tbl) => {
      const label = dryRun ? `${tbl.rows_inserted} ${t("result.would_insert")}` : `${tbl.rows_inserted} rows`;
      const status = tbl.success
        ? `<span class="ok-text">✓ ${label}</span>`
        : `<span class="err-text">✗ ${esc(tbl.error || "cancelled")}</span>`;
      return `<tr><td>${esc(tbl.table_name)}</td><td>${status}</td></tr>`;
    })
    .join("");

  document.getElementById("result-table-body").innerHTML = rows;

  // After dry run: show Back button so user can go back and run real sync
  const backFromResult = document.getElementById("back-from-result");
  if (dryRun) {
    backFromResult.classList.remove("hidden");
  } else {
    backFromResult.classList.add("hidden");
  }
}

document.getElementById("back-from-result").addEventListener("click", () => {
  showStep("step-confirm");
});

document.getElementById("restart-btn").addEventListener("click", () => {
  // Reset state completely
  state.sessionId = null;
  state.appName = null;
  state.tables = [];
  state.currentJobId = null;
  if (state.currentEventSource) {
    state.currentEventSource.close();
    state.currentEventSource = null;
  }

  // Reset form fields
  document.getElementById("upload-form").reset();
  document.getElementById("csv-files").value = "";

  hideError("upload-error");
  hideError("sync-error");
  document.getElementById("back-from-result").classList.add("hidden");
  showStep("step-upload");
});

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------
function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = loading;
  btn.dataset.originalText = btn.dataset.originalText || btn.textContent;
  btn.textContent = loading ? t("btn.loading") : btn.dataset.originalText;
}

function showError(elemId, msg) {
  const el = document.getElementById(elemId);
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
}

function hideError(elemId) {
  const el = document.getElementById(elemId);
  if (el) el.classList.add("hidden");
}

// ---------------------------------------------------------------------------
// Init — apply translations on load
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  applyTranslations();
});
