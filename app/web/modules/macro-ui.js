(function initMacroUi(global) {
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
    if (!value) return "unknown";
    return String(value).replace("T", " ").replace("Z", "").slice(0, 16);
  }

  function statusClass(value) {
    const key = String(value || "").toLowerCase();
    if (["ok", "success", "completed", "available", "pass"].includes(key)) return "ok";
    if (["failed", "fail", "error", "unavailable"].includes(key)) return "fail";
    if (["partial", "warn", "warning", "stale", "missing"].includes(key)) return "warn";
    return "neutral";
  }

  function metric(label, value, status) {
    return `
      <div class="decision-metric ${escapeHtml(statusClass(status))}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value ?? "-")}</strong>
      </div>
    `;
  }

  function providerHealth(data = {}) {
    const providers = Array.isArray(data.providers) ? data.providers : [];
    const stale = Array.isArray(data.stale_series) ? data.stale_series : [];
    const staleLabels = stale
      .map((item) => (typeof item === "string" ? item : (item?.series_id || item?.display_name || item?.status || "")))
      .filter(Boolean);
    const scheduler = data.scheduler || {};
    return `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(statusClass(data.status))}">${escapeHtml(data.status || "unknown")}</span>
        <span>generated ${escapeHtml(fmtDate(data.generated_at))} / stale ${escapeHtml(fmtNumber(staleLabels.length))}</span>
      </div>
      <div class="decision-metric-grid dense">
        ${metric("Providers", fmtNumber(providers.length), providers.length ? "ok" : "warn")}
        ${metric("Enabled", fmtNumber(providers.filter((item) => item.enabled).length), "ok")}
        ${metric("Configured", fmtNumber(providers.filter((item) => item.configured).length), "ok")}
        ${metric("Scheduler", scheduler.enabled ? "on" : "off", scheduler.enabled ? "ok" : "warn")}
      </div>
      ${(data.warnings || []).length ? `<div class="macro-warning">${escapeHtml(data.warnings.join(" "))}</div>` : ""}
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>Provider</th><th>Enabled</th><th>Configured</th><th>Latest status</th><th>Rows</th><th>Error</th></tr></thead>
          <tbody>
            ${providers.map((item) => `
              <tr>
                <td>${escapeHtml(item.provider || "")}</td>
                <td>${escapeHtml(item.enabled ? "yes" : "no")}</td>
                <td>${escapeHtml(item.configured ? "yes" : "no")}</td>
                <td><span class="table-status ${escapeHtml(statusClass(item.latest_status))}">${escapeHtml(item.latest_status || "unknown")}</span></td>
                <td>${escapeHtml(fmtNumber(item.latest_rows || 0))}</td>
                <td>${escapeHtml(item.latest_error || "-")}</td>
              </tr>
            `).join("") || `<tr><td colspan="6">No provider status is available.</td></tr>`}
          </tbody>
        </table>
      </div>
      ${staleLabels.length ? `<div class="macro-warning">Stale series: ${escapeHtml(staleLabels.slice(0, 12).join(", "))}${staleLabels.length > 12 ? " ..." : ""}</div>` : ""}
    `;
  }

  global.FinGPTMacroUi = {
    providerHealth,
  };
})(window);
