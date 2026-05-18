(function initQuantUi(global) {
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtNumber(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num.toLocaleString("en-US") : "0";
  }

  function fmtDate(value) {
    if (!value) return "-";
    return String(value).replace("T", " ").replace("Z", "").slice(0, 16);
  }

  function compactPath(value) {
    const text = String(value || "");
    if (text.length <= 54) return text;
    return `${text.slice(0, 20)}...${text.slice(-28)}`;
  }

  function statusClass(status) {
    const key = String(status || "").toLowerCase();
    if (["ok", "success", "completed", "valid"].includes(key)) return "ok";
    if (["failed", "fail", "error", "invalid"].includes(key)) return "fail";
    if (["partial", "warn", "warning", "stale"].includes(key)) return "warn";
    return "neutral";
  }

  function empty(message) {
    return `<div class="home-news-empty">${escapeHtml(message)}</div>`;
  }

  function exportStorageReport(data = {}) {
    const topRuns = Array.isArray(data.top_runs) ? data.top_runs : [];
    const staleExports = Array.isArray(data.stale_exports) ? data.stale_exports : [];
    const formatCounts = data.format_counts || {};
    const manifestStatuses = data.manifest_status_counts || {};
    const formatText = Object.keys(formatCounts).length
      ? Object.entries(formatCounts).map(([key, value]) => `${key}:${fmtNumber(value)}`).join(", ")
      : "none";
    const manifestText = Object.keys(manifestStatuses).length
      ? Object.entries(manifestStatuses).map(([key, value]) => `${key}:${fmtNumber(value)}`).join(", ")
      : "none";
    return `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(statusClass(data.status || "success"))}">${escapeHtml(data.status || "success")}</span>
        <span>cross-run export storage report</span>
      </div>
      <div class="decision-chip-row">
        <span>runs ${escapeHtml(fmtNumber(data.run_count || 0))}</span>
        <span>with exports ${escapeHtml(fmtNumber(data.runs_with_exports || 0))}</span>
        <span>export dirs ${escapeHtml(fmtNumber(data.export_directory_count || 0))}</span>
        <span>bytes ${escapeHtml(fmtNumber(data.total_bytes || 0))}</span>
        <span>stale ${escapeHtml(fmtNumber(data.stale_export_count || 0))}</span>
        <button type="button" class="linkish decision-inline-action" data-action="cross-run-cleanup-preview" data-keep-last="1" data-stale-after-days="0">cleanup preview</button>
      </div>
      <div class="decision-list compact">
        <div class="decision-list-row"><span>Formats</span><strong>${escapeHtml(formatText)}</strong></div>
        <div class="decision-list-row"><span>Manifest status</span><strong>${escapeHtml(manifestText)}</strong></div>
        <div class="decision-list-row"><span>Oldest export</span><strong>${escapeHtml(data.oldest_export_generated_at || "-")}</strong></div>
        <div class="decision-list-row"><span>Newest export</span><strong>${escapeHtml(data.newest_export_generated_at || "-")}</strong></div>
        <div class="decision-list-row"><span>Root</span><strong>${escapeHtml(compactPath(data.artifact_root || ""))}</strong></div>
      </div>
      <div class="decision-section-title">Largest runs by generated export storage</div>
      ${topRuns.length ? `
        <div class="decision-table-wrap">
          <table class="decision-table">
            <thead><tr><th>Run</th><th>Exports</th><th>Bytes</th><th>Rows</th><th>Formats</th><th>Newest</th><th>Open</th></tr></thead>
            <tbody>
              ${topRuns.map((item) => `
                <tr>
                  <td>${escapeHtml(item.run_id || "")}</td>
                  <td>${escapeHtml(fmtNumber(item.export_count || 0))}</td>
                  <td>${escapeHtml(fmtNumber(item.total_bytes || 0))}</td>
                  <td>${escapeHtml(fmtNumber(item.total_rows || 0))}</td>
                  <td>${escapeHtml(Object.keys(item.formats || {}).join(", ") || "-")}</td>
                  <td>${escapeHtml(fmtDate(item.newest_export_generated_at || ""))}</td>
                  <td><button type="button" class="linkish" data-testid="quant-run-open" aria-label="Open quant run ${escapeHtml(item.run_id || "")}" data-quant-run-id="${escapeHtml(item.run_id || "")}">open</button></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : empty("No generated artifact exports are present yet.")}
      <div class="decision-section-title">Old export candidates</div>
      ${staleExports.length ? `
        <div class="decision-table-wrap">
          <table class="decision-table">
            <thead><tr><th>Run</th><th>Format</th><th>Age</th><th>Bytes</th><th>Status</th><th>Manifest</th></tr></thead>
            <tbody>
              ${staleExports.map((item) => `
                <tr>
                  <td>${escapeHtml(item.run_id || "")}</td>
                  <td>${escapeHtml(item.format || "")}</td>
                  <td>${escapeHtml(fmtNumber(item.age_days || 0))}d</td>
                  <td>${escapeHtml(fmtNumber(item.total_bytes || 0))}</td>
                  <td><span class="table-status ${escapeHtml(statusClass(item.status || "unknown"))}">${escapeHtml(item.status || "unknown")}</span></td>
                  <td>${escapeHtml(compactPath(item.manifest_path || ""))}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : empty("No export directories exceed the stale-age threshold.")}
    `;
  }

  global.FinGPTQuantUi = {
    exportStorageReport,
  };
})(window);
