(function initMarketUi(global) {
  const ORDER = ["SPY", "QQQ", "TLT", "HYG", "LQD", "GLD", "BTC-USD", "DX-Y.NYB", "^TNX"];

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtNumber(value, digits = 2) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "-";
    return num.toFixed(digits).replace(/\.?0+$/, "");
  }

  function fmtPct(value) {
    const num = Number(value);
    return Number.isFinite(num) ? `${fmtNumber(num, 2)}%` : "-";
  }

  function fmtDate(value) {
    if (!value) return "-";
    return String(value).replace("T", " ").replace("Z", "").slice(0, 16);
  }

  function statusClass(value) {
    const key = String(value || "").toLowerCase();
    if (["ok", "success", "completed", "pass", "available"].includes(key)) return "ok";
    if (["fail", "failed", "error", "unavailable"].includes(key)) return "fail";
    if (["partial", "warn", "warning", "stale"].includes(key)) return "warn";
    return "neutral";
  }

  function returnClass(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "muted";
    if (num > 0) return "ok";
    if (num < 0) return "fail";
    return "muted";
  }

  function metric(label, value, status) {
    return `
      <div class="decision-metric ${escapeHtml(statusClass(status))}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value ?? "-")}</strong>
      </div>
    `;
  }

  function empty(message) {
    return `<div class="home-news-empty">${escapeHtml(message)}</div>`;
  }

  function marketTape(overview, options = {}) {
    const freshnessLabels = options.freshnessLabels || {};
    const tape = Array.isArray(overview?.market_tape)
      ? overview.market_tape.slice().sort((a, b) => {
          const aIdx = ORDER.indexOf(String(a?.symbol || "").toUpperCase());
          const bIdx = ORDER.indexOf(String(b?.symbol || "").toUpperCase());
          return (aIdx >= 0 ? aIdx : ORDER.length) - (bIdx >= 0 ? bIdx : ORDER.length);
        })
      : [];
    const freshness = overview?.freshness_summary || {};
    const heatmap = overview?.heatmap_summary || {};
    const asOf = overview?.raw_market_meta?.generated_at ? fmtDate(overview.raw_market_meta.generated_at) : "basis time unknown";
    const meta = `${freshness.decision_usable_count || 0}/${freshness.item_count || 0} usable / ${heatmap.status || "heatmap"} / ${asOf}`;
    if (!tape.length) return { meta, html: empty("No market tape data is available.") };

    const metrics = [
      metric("Market freshness", `${freshness.decision_usable_count || 0}/${freshness.item_count || 0}`, freshness.status || "unavailable"),
      metric("Heatmap universe", heatmap.universe_size ? `${heatmap.decision_usable_count || 0}/${heatmap.universe_size}` : "not loaded", heatmap.status || "unavailable"),
      metric("Latest heatmap", heatmap.latest_as_of ? fmtDate(heatmap.latest_as_of) : "unknown", heatmap.status || "unavailable"),
      metric("Advisory", overview?.advisory_only ? "advisory only" : "needs review", overview?.advisory_only ? "ok" : "warn"),
    ].join("");
    const rows = tape.map((item) => {
      const cls = item.is_decision_usable ? returnClass(item.return_1d) : "warn";
      const monthCls = item.is_decision_usable ? returnClass(item.return_1m) : "warn";
      const freshnessLabel = freshnessLabels[item.freshness_status] || item.freshness_status || "unknown";
      const itemAsOf = item.as_of ? fmtDate(item.as_of) : freshnessLabel;
      return `
        <article class="market-tape-item ${escapeHtml(cls)} ${item.is_decision_usable ? "" : "stale"}">
          <div class="market-tape-symbol-row">
            <strong>${escapeHtml(item.symbol || "")}</strong>
            <span>${escapeHtml(item.asset_class || "")}</span>
          </div>
          <div class="market-tape-label">${escapeHtml(item.label || "")}</div>
          <div class="market-tape-price">${item.price === null || item.price === undefined ? "-" : escapeHtml(String(item.price))}</div>
          <div class="market-tape-returns">
            <span class="market-tape-return ${escapeHtml(cls)}">1D ${escapeHtml(fmtPct(item.return_1d))}</span>
            <span class="market-tape-return ${escapeHtml(monthCls)}">1M ${escapeHtml(fmtPct(item.return_1m))}</span>
          </div>
          <div class="market-tape-meta">
            <span>${escapeHtml(itemAsOf)}</span>
            <span>${escapeHtml(item.source || "unknown")}</span>
          </div>
        </article>
      `;
    }).join("");
    const warning = [freshness.warning, heatmap.warning].filter(Boolean).join(" ");
    return {
      meta,
      html: `
        <div class="decision-metric-grid dense">${metrics}</div>
        ${warning ? `<div class="decision-summary warn">${escapeHtml(warning)}</div>` : ""}
        <div class="market-tape-grid">${rows}</div>
      `,
    };
  }

  function marketSignals(overview) {
    const signals = Array.isArray(overview?.signals) ? overview.signals : [];
    if (!signals.length) return empty("No market signals are available.");
    return signals.map((signal) => {
      const cls = statusClass(signal.status);
      const evidence = Array.isArray(signal.evidence) ? signal.evidence.slice(0, 6) : [];
      return `
        <article class="market-signal-item ${escapeHtml(cls)}">
          <div class="decision-status-row">
            <span class="decision-badge ${escapeHtml(cls)}">${escapeHtml(signal.status || "unknown")}</span>
            <span>${escapeHtml(signal.signal_id || "")}</span>
          </div>
          <h4>${escapeHtml(signal.title || "")}</h4>
          <p>${escapeHtml(signal.summary || "")}</p>
          <div class="market-signal-evidence">
            ${evidence.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
          </div>
          <div class="market-signal-note">${escapeHtml(signal.interpretation || "")}</div>
        </article>
      `;
    }).join("");
  }

  global.FinGPTMarketUi = {
    marketTape,
    marketSignals,
  };
})(window);
