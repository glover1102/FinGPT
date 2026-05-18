(function initForecastUi(global) {
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function empty(message) {
    return `<div class="home-news-empty">${escapeHtml(message)}</div>`;
  }

  function statusClass(status) {
    const key = String(status || "").toLowerCase();
    if (key === "succeeded") return "ok";
    if (key === "failed" || key === "cancelled") return "fail";
    if (key === "running" || key === "queued") return "warn";
    return "neutral";
  }

  function jobs(items) {
    if (!Array.isArray(items) || !items.length) return empty("No Forecast jobs have been submitted.");
    return `
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>Job</th><th>Status</th><th>Ticker</th><th>Model</th><th>Stage</th><th>Result</th><th>Action</th></tr></thead>
          <tbody>
            ${items.map((item) => {
              const summary = item.result_summary || {};
              const experimentId = summary.experiment_id || "";
              const canCancel = item.can_cancel && !["succeeded", "failed", "cancelled"].includes(item.job_status);
              const canRetry = item.can_retry || ["failed", "cancelled"].includes(item.job_status);
              return `
                <tr>
                  <td>${escapeHtml(item.job_id || "")}</td>
                  <td><span class="decision-badge ${escapeHtml(statusClass(item.job_status))}">${escapeHtml(item.job_status || "")}</span></td>
                  <td>${escapeHtml(item.ticker || "")}</td>
                  <td>${escapeHtml(item.model_name || "")}</td>
                  <td>${escapeHtml(item.progress_stage || "")}<br><span class="muted">${escapeHtml(item.progress_message || "")}</span></td>
                  <td>${experimentId ? `<button type="button" class="linkish" data-action="forecast-experiment-detail" data-experiment-id="${escapeHtml(experimentId)}">${escapeHtml(experimentId)}</button>` : escapeHtml(summary.status || "")}</td>
                  <td>
                    <button type="button" class="linkish" data-action="forecast-job-refresh" data-job-id="${escapeHtml(item.job_id || "")}">refresh</button>
                    ${canCancel ? `<button type="button" class="linkish" data-action="forecast-job-cancel" data-job-id="${escapeHtml(item.job_id || "")}">cancel</button>` : ""}
                    ${canRetry ? `<button type="button" class="linkish" data-action="forecast-job-retry" data-job-id="${escapeHtml(item.job_id || "")}">retry</button>` : ""}
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  global.FinGPTForecastUi = {
    jobs,
  };
})(window);
