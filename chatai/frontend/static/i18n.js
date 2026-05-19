// i18n.js — Translations for EN / ES

const TRANSLATIONS = {
  en: {
    // Header
    "app.title": "AppSheet → PostgreSQL Migrator",
    "app.subtitle": "Upload CSVs, validate schema, preview data, then sync to PostgreSQL.",

    // Step labels
    "step1.title": "Upload CSV files",
    "step2.title": "Validation results",
    "step3.title": "Confirm sync",
    "step4.title": "Sync Complete",
    "step4.dryrun.title": "Dry Run Complete — No data was written",

    // Step 1
    "upload.app_name.label": "App name",
    "upload.app_name.hint": "Tables will be created as <code>appsheet.&lt;app_name&gt;_&lt;table&gt;</code>",
    "upload.files.label": "CSV files",
    "upload.files.hint": "Table name is derived from filename. <code>empresa.csv</code> → <code>appsheet.app_empresa</code>",
    "upload.btn": "Upload & Analyse",

    // Step 2
    "validate.col.column": "Column",
    "validate.col.type": "Type",
    "validate.col.empty": "Empty",
    "validate.col.warnings": "Warnings",
    "validate.preview_btn": "Preview first 20 rows",
    "validate.back": "← Back",
    "validate.confirm": "Review & Confirm →",
    "validate.badge.clean": "✓ clean",
    "validate.badge.warnings": "⚠ warnings",

    // Step 3
    "confirm.app": "App",
    "confirm.schema": "Schema pattern",
    "confirm.total_rows": "Total rows to insert",
    "confirm.col.table": "Table",
    "confirm.col.rows": "Rows",
    "confirm.col.columns": "Columns",
    "confirm.col.warnings": "Warnings",
    "confirm.back": "← Back",
    "confirm.dryrun": "Dry Run (validate only)",
    "confirm.sync": "Confirm & Sync →",

    // Step 4
    "result.app": "App",
    "result.schema": "Schema pattern",
    "result.rows_inserted": "Total rows inserted",
    "result.rows_validated": "Rows validated (would be inserted)",
    "result.dryrun_note": "⚠ Dry run — database was NOT modified. Go back to run the real sync.",
    "result.col.table": "Table",
    "result.col.result": "Result",
    "result.back": "← Back to confirm",
    "result.restart": "Start new migration",
    "result.would_insert": "rows (would insert)",

    // Preview modal
    "preview.title": "Preview",
    "preview.showing": "Showing",
    "preview.of": "of first 20 rows",

    // Overlay
    "overlay.uploading": "Uploading and analysing {n} file(s)…",
    "overlay.syncing": "Syncing data to PostgreSQL…",
    "overlay.dryrun": "Running dry run validation…",
    "overlay.stopping": "Stopping…",
    "overlay.stop": "Stop",

    // Errors
    "error.app_required": "App name is required.",
    "error.files_required": "Please select at least one CSV file.",
    "error.session_expired": "⚠ Session expired — the server was restarted. Please go back and re-upload your files.",
    "error.network": "Network error: ",
    "error.sync_failed": "Failed to start sync",
    "error.connection_lost": "Connection to server lost during sync.",
    "error.files_had_errors": "Some files had errors:\n",

    // Loading states
    "btn.loading": "Loading...",

    // Warning labels
    "warn.warnings": "warning(s)",
  },

  es: {
    // Header
    "app.title": "AppSheet → PostgreSQL Migrador",
    "app.subtitle": "Sube CSVs, valida el esquema, previsualiza los datos y sincroniza con PostgreSQL.",

    // Step labels
    "step1.title": "Subir archivos CSV",
    "step2.title": "Resultados de validación",
    "step3.title": "Confirmar sincronización",
    "step4.title": "Sincronización completa",
    "step4.dryrun.title": "Prueba en seco completa — No se escribió nada",

    // Step 1
    "upload.app_name.label": "Nombre de la app",
    "upload.app_name.hint": "Las tablas se crearán como <code>appsheet.&lt;app_name&gt;_&lt;tabla&gt;</code>",
    "upload.files.label": "Archivos CSV",
    "upload.files.hint": "El nombre de la tabla se deduce del nombre del archivo. <code>empresa.csv</code> → <code>appsheet.app_empresa</code>",
    "upload.btn": "Subir y analizar",

    // Step 2
    "validate.col.column": "Columna",
    "validate.col.type": "Tipo",
    "validate.col.empty": "Vacíos",
    "validate.col.warnings": "Advertencias",
    "validate.preview_btn": "Ver primeras 20 filas",
    "validate.back": "← Volver",
    "validate.confirm": "Revisar y confirmar →",
    "validate.badge.clean": "✓ limpio",
    "validate.badge.warnings": "⚠ advertencias",

    // Step 3
    "confirm.app": "App",
    "confirm.schema": "Patrón de esquema",
    "confirm.total_rows": "Total de filas a insertar",
    "confirm.col.table": "Tabla",
    "confirm.col.rows": "Filas",
    "confirm.col.columns": "Columnas",
    "confirm.col.warnings": "Advertencias",
    "confirm.back": "← Volver",
    "confirm.dryrun": "Prueba en seco (solo validar)",
    "confirm.sync": "Confirmar y sincronizar →",

    // Step 4
    "result.app": "App",
    "result.schema": "Patrón de esquema",
    "result.rows_inserted": "Total de filas insertadas",
    "result.rows_validated": "Filas validadas (se insertarían)",
    "result.dryrun_note": "⚠ Prueba en seco — la base de datos NO fue modificada. Vuelve atrás para sincronizar.",
    "result.col.table": "Tabla",
    "result.col.result": "Resultado",
    "result.back": "← Volver a confirmar",
    "result.restart": "Nueva migración",
    "result.would_insert": "filas (se insertarían)",

    // Preview modal
    "preview.title": "Vista previa",
    "preview.showing": "Mostrando",
    "preview.of": "de las primeras 20 filas",

    // Overlay
    "overlay.uploading": "Subiendo y analizando {n} archivo(s)…",
    "overlay.syncing": "Sincronizando datos con PostgreSQL…",
    "overlay.dryrun": "Ejecutando prueba en seco…",
    "overlay.stopping": "Deteniendo…",
    "overlay.stop": "Detener",

    // Errors
    "error.app_required": "El nombre de la app es requerido.",
    "error.files_required": "Por favor selecciona al menos un archivo CSV.",
    "error.session_expired": "⚠ Sesión expirada — el servidor fue reiniciado. Por favor vuelve a subir tus archivos.",
    "error.network": "Error de red: ",
    "error.sync_failed": "No se pudo iniciar la sincronización",
    "error.connection_lost": "Se perdió la conexión con el servidor durante la sincronización.",
    "error.files_had_errors": "Algunos archivos tuvieron errores:\n",

    // Loading states
    "btn.loading": "Cargando...",

    // Warning labels
    "warn.warnings": "advertencia(s)",
  },
};

// ---------------------------------------------------------------------------
// i18n API
// ---------------------------------------------------------------------------
let _currentLang = localStorage.getItem("lang") || "es";

function t(key, vars = {}) {
  const dict = TRANSLATIONS[_currentLang] || TRANSLATIONS["en"];
  let str = dict[key] || TRANSLATIONS["en"][key] || key;
  for (const [k, v] of Object.entries(vars)) {
    str = str.replace(`{${k}}`, v);
  }
  return str;
}

function setLang(lang) {
  _currentLang = lang;
  localStorage.setItem("lang", lang);
  applyTranslations();
}

function getLang() {
  return _currentLang;
}

// Apply translations to all static elements with data-i18n attribute
function applyTranslations() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    const val = t(key);
    if (el.tagName === "INPUT" && el.placeholder !== undefined) {
      el.placeholder = val;
    } else {
      el.innerHTML = val;
    }
  });

  // Update lang toggle buttons
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("lang-btn--active", btn.dataset.lang === _currentLang);
  });
}
