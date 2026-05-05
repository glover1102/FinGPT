/* =============================================================
   FinGPT Local Research Assistant — UI Controller
   ============================================================= */

const API = {
  config: "/api/v1/config",
  analyze: "/api/v1/research/analyze",
  stream: "/api/v1/research/stream",
  universal: "/api/v1/research/universal",
  universalStream: "/api/v1/research/universal/stream",
  compare: "/api/v1/research/compare",
  watchlist: "/api/v1/watchlist",
  latest: "/api/v1/outputs/latest",
  reportMd: "/api/v1/outputs/report.md",
  reportHtml: "/api/v1/outputs/report.html",
  health: "/api/v1/health",
  runs: "/api/v1/runs",
  run: (id) => `/api/v1/runs/${encodeURIComponent(id)}`,
  runSummary: (ticker) => `/api/v1/runs/summary/${encodeURIComponent(ticker)}`,
  preflight: "/api/v1/preflight",
  preflightForce: "/api/v1/preflight?force=true",
  runbookFailureModes: "/api/v1/runbook/failure-modes",
  qdrantInfo: "/api/v1/qdrant/collection",
  qdrantPurge: "/api/v1/qdrant/purge",
  evalDashboard: "/api/v1/eval/dashboard",
  dashboardNews: "/api/v1/dashboard/news?limit=20",
  dashboardMarket: "/api/v1/dashboard/market",
  dashboardEquityHeatmap: "/api/v1/dashboard/equity-heatmap",
  dataHealth: "/api/v1/data/health",
  dataPrices: (ticker, limit = 252) => `/api/v1/data/prices/${encodeURIComponent(ticker)}?limit=${encodeURIComponent(limit)}`,
  backtestRun: "/api/v1/backtest/run",
  quantFeatures: "/api/v1/quant/features/preview",
  quantSignals: "/api/v1/quant/signals/generate",
  quantBacktest: "/api/v1/quant/backtest",
  quantBacktests: "/api/v1/quant/backtests",
  quantBacktestBundle: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/bundle`,
  quantBacktestReplay: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/replay`,
  quantBacktestReplayReports: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/replay-reports`,
  quantBacktestExport: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/export`,
  quantBacktestExports: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/exports`,
  quantBacktestExportCleanupPreview: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/exports/cleanup-preview`,
  quantBacktestExportCleanup: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/exports/cleanup`,
  quantBacktestExportVerify: (runId) => `/api/v1/quant/backtest/${encodeURIComponent(runId)}/export/verify`,
  quantExportStorage: "/api/v1/quant/exports/storage",
  quantExportCleanupPreview: "/api/v1/quant/exports/cleanup-preview",
  quantExportCleanup: "/api/v1/quant/exports/cleanup",
  quantStrategies: "/api/v1/quant/strategy/list",
  quantStrategy: (strategyId) => `/api/v1/quant/strategy/${encodeURIComponent(strategyId)}`,
  quantStrategyDryRun: "/api/v1/quant/strategy/dry-run",
  quantStrategySave: "/api/v1/quant/strategy/save",
  portfolioOptimize: "/api/v1/portfolio/optimize",
};

const STORAGE = {
  history: "fingpt.history.v1",
  form: "fingpt.form.v1",
};

const STAGES = ["collect", "ingest", "retrieve", "infer", "analyze", "report", "output"];

const els = {
  homeBtn: document.getElementById("homeBtn"),
  form: document.getElementById("analysisForm"),
  ticker: document.getElementById("ticker"),
  researchModeInputs: () => document.querySelectorAll('input[name="researchMode"]'),
  tickerChips: document.getElementById("tickerChips"),
  question: document.getElementById("question"),
  presetChips: document.getElementById("presetChips"),
  sourceInputs: () => document.querySelectorAll('input[name="source"]'),
  lookback: document.getElementById("lookback"),
  lookbackValue: document.getElementById("lookbackValue"),
  topk: document.getElementById("topk"),
  topkValue: document.getElementById("topkValue"),
  model: document.getElementById("model"),
  runBtn: document.getElementById("runBtn"),
  loadLatestBtn: document.getElementById("loadLatestBtn"),
  clearHistoryBtn: document.getElementById("clearHistoryBtn"),
  historyToggleBtn: document.getElementById("historyToggleBtn"),
  historySummary: document.getElementById("historySummary"),
  historyList: document.getElementById("historyList"),
  healthPill: document.getElementById("healthPill"),

  preflightPill: document.getElementById("preflightPill"),
  preflightDot: document.getElementById("preflightDot"),
  preflightLabel: document.getElementById("preflightLabel"),
  preflightPanel: document.getElementById("preflightPanel"),
  preflightSubtitle: document.getElementById("preflightSubtitle"),
  preflightChecks: document.getElementById("preflightChecks"),
  preflightRunbook: document.getElementById("preflightRunbook"),
  preflightRefresh: document.getElementById("preflightRefresh"),
  preflightClose: document.getElementById("preflightClose"),

  qdrantAdminBtn: document.getElementById("qdrantAdminBtn"),
  qdrantPanel: document.getElementById("qdrantPanel"),
  qdrantSubtitle: document.getElementById("qdrantSubtitle"),
  qdrantStats: document.getElementById("qdrantStats"),
  qdrantBreakdownList: document.getElementById("qdrantBreakdownList"),
  qdrantBreakdownNote: document.getElementById("qdrantBreakdownNote"),
  qdrantRefresh: document.getElementById("qdrantRefresh"),
  qdrantClose: document.getElementById("qdrantClose"),
  qdrantPurgeDays: document.getElementById("qdrantPurgeDays"),
  qdrantPurgeTicker: document.getElementById("qdrantPurgeTicker"),
  qdrantPurgeDryRun: document.getElementById("qdrantPurgeDryRun"),
  qdrantPurgeRun: document.getElementById("qdrantPurgeRun"),
  qdrantPurgeResult: document.getElementById("qdrantPurgeResult"),

  qualityDashBtn: document.getElementById("qualityDashBtn"),
  qualityPanel: document.getElementById("qualityPanel"),
  qualitySubtitle: document.getElementById("qualitySubtitle"),
  qualitySummary: document.getElementById("qualitySummary"),
  qualityCategories: document.getElementById("qualityCategories"),
  qualityCases: document.getElementById("qualityCases"),
  qualityCasesNote: document.getElementById("qualityCasesNote"),
  qualityReport: document.getElementById("qualityReport"),
  qualityRefresh: document.getElementById("qualityRefresh"),
  qualityClose: document.getElementById("qualityClose"),

  tickerSummary: document.getElementById("tickerSummary"),
  sparkline: document.getElementById("sparkline"),
  sparklineLabel: document.getElementById("sparklineLabel"),

  emptyState: document.getElementById("emptyState"),
  loadingState: document.getElementById("loadingState"),
  loadingTicker: document.getElementById("loadingTicker"),
  loadingSub: document.getElementById("loadingSub"),
  loadingTimer: document.getElementById("loadingTimer"),
  progressStages: document.getElementById("progressStages"),

  resultView: document.getElementById("resultView"),
  resTicker: document.getElementById("resTicker"),
  resStatus: document.getElementById("resStatus"),
  resCacheBadge: document.getElementById("resCacheBadge"),
  compareMode: document.getElementById("compareMode"),
  tickerHint: document.getElementById("tickerHint"),
  compareView: document.getElementById("compareView"),
  compareMeta: document.getElementById("compareMeta"),
  compareTable: document.getElementById("compareTable"),
  compareSummaries: document.getElementById("compareSummaries"),
  watchlistList: document.getElementById("watchlistList"),
  watchlistAddBtn: document.getElementById("watchlistAddBtn"),
  watchlistSchedStatus: document.getElementById("watchlistSchedStatus"),
  resQuestion: document.getElementById("resQuestion"),
  errorBanner: document.getElementById("errorBanner"),
  resSentiment: document.getElementById("resSentiment"),
  resConfidence: document.getElementById("resConfidence"),
  confidenceFill: document.getElementById("confidenceFill"),
  resCitationCount: document.getElementById("resCitationCount"),
  resChunkCount: document.getElementById("resChunkCount"),

  tabs: document.querySelectorAll(".tab"),
  tabPanels: document.querySelectorAll(".tab-panel"),

  resSummary: document.getElementById("resSummary"),
  resConclusion: document.getElementById("resConclusion"),
  metricsTable: document.getElementById("metricsTable"),
  quantSnapshot: document.getElementById("quantSnapshot"),
  riskPanel: document.getElementById("riskPanel"),
  scenarioPanel: document.getElementById("scenarioPanel"),
  bullList: document.getElementById("bullList"),
  bearList: document.getElementById("bearList"),
  evidenceList: document.getElementById("evidenceList"),
  evidenceSearch: document.getElementById("evidenceSearch"),
  citationsList: document.getElementById("citationsList"),
  diagRequest: document.getElementById("diagRequest"),
  diagInference: document.getElementById("diagInference"),
  stageTimeline: document.getElementById("stageTimeline"),
  sourceResultsBody: document.getElementById("sourceResultsBody"),
  providerResultsBody: document.getElementById("providerResultsBody"),
  diagRetrieval: document.getElementById("diagRetrieval"),
  reportMd: document.getElementById("reportMd"),
  rawJson: document.getElementById("rawJson"),

  downloadMdBtn: document.getElementById("downloadMdBtn"),
  downloadJsonBtn: document.getElementById("downloadJsonBtn"),
  openHtmlBtn: document.getElementById("openHtmlBtn"),
  formNotice: document.getElementById("formNotice"),
  homeNewsList: document.getElementById("homeNewsList"),
  homeNewsCategories: document.getElementById("homeNewsCategories"),
  homeNewsRefresh: document.getElementById("homeNewsRefresh"),
  homeSurfaceGrid: document.getElementById("homeSurfaceGrid"),
  marketDashboardTab: document.getElementById("marketDashboardTab"),
  quantLabTab: document.getElementById("quantLabTab"),
  homeHeatmap: document.getElementById("homeHeatmap"),
  homeHeatmapMeta: document.getElementById("homeHeatmapMeta"),
  homeHeatmapRefresh: document.getElementById("homeHeatmapRefresh"),
  homeMarketList: document.getElementById("homeMarketList"),
  dataHealthRefresh: document.getElementById("dataHealthRefresh"),
  homeDataHealth: document.getElementById("homeDataHealth"),
  assetDetailTicker: document.getElementById("assetDetailTicker"),
  assetDetailLoad: document.getElementById("assetDetailLoad"),
  assetDetailSurface: document.getElementById("assetDetailSurface"),
  backtestTicker: document.getElementById("backtestTicker"),
  backtestUniverseOpen: document.getElementById("backtestUniverseOpen"),
  backtestUniverseChips: document.getElementById("backtestUniverseChips"),
  backtestStrategy: document.getElementById("backtestStrategy"),
  backtestStrategyRegistry: document.getElementById("backtestStrategyRegistry"),
  backtestBenchmark: document.getElementById("backtestBenchmark"),
  backtestBenchmarkCompare: document.getElementById("backtestBenchmarkCompare"),
  backtestStartDate: document.getElementById("backtestStartDate"),
  backtestEndDate: document.getElementById("backtestEndDate"),
  backtestLookbackDays: document.getElementById("backtestLookbackDays"),
  backtestShortWindow: document.getElementById("backtestShortWindow"),
  backtestLongWindow: document.getElementById("backtestLongWindow"),
  backtestTopN: document.getElementById("backtestTopN"),
  backtestRebalanceEvery: document.getElementById("backtestRebalanceEvery"),
  backtestFreshnessProfile: document.getElementById("backtestFreshnessProfile"),
  backtestRequireFresh: document.getElementById("backtestRequireFresh"),
  backtestUseResearchScore: document.getElementById("backtestUseResearchScore"),
  backtestCostBps: document.getElementById("backtestCostBps"),
  backtestSlippageBps: document.getElementById("backtestSlippageBps"),
  backtestRun: document.getElementById("backtestRun"),
  backtestSurface: document.getElementById("backtestSurface"),
  quantFeatureRun: document.getElementById("quantFeatureRun"),
  quantFeatureSurface: document.getElementById("quantFeatureSurface"),
  quantSignalRun: document.getElementById("quantSignalRun"),
  quantSignalSurface: document.getElementById("quantSignalSurface"),
  quantStrategyRefresh: document.getElementById("quantStrategyRefresh"),
  quantStrategyNewDraft: document.getElementById("quantStrategyNewDraft"),
  quantStrategyDryRun: document.getElementById("quantStrategyDryRun"),
  quantStrategySave: document.getElementById("quantStrategySave"),
  quantStrategyDelete: document.getElementById("quantStrategyDelete"),
  strategyDefinitionJson: document.getElementById("strategyDefinitionJson"),
  quantStrategySurface: document.getElementById("quantStrategySurface"),
  quantStrategyResultSurface: document.getElementById("quantStrategyResultSurface"),
  quantRunHistoryRefresh: document.getElementById("quantRunHistoryRefresh"),
  quantExportStorageReport: document.getElementById("quantExportStorageReport"),
  quantCrossRunCleanupPreview: document.getElementById("quantCrossRunCleanupPreview"),
  quantRunHistorySurface: document.getElementById("quantRunHistorySurface"),
  portfolioTickers: document.getElementById("portfolioTickers"),
  portfolioMethod: document.getElementById("portfolioMethod"),
  portfolioBenchmark: document.getElementById("portfolioBenchmark"),
  portfolioCovarianceMethod: document.getElementById("portfolioCovarianceMethod"),
  portfolioShrinkageAlpha: document.getElementById("portfolioShrinkageAlpha"),
  portfolioStartDate: document.getElementById("portfolioStartDate"),
  portfolioEndDate: document.getElementById("portfolioEndDate"),
  portfolioLookbackDays: document.getElementById("portfolioLookbackDays"),
  portfolioMaxWeight: document.getElementById("portfolioMaxWeight"),
  portfolioSyncBacktest: document.getElementById("portfolioSyncBacktest"),
  portfolioOptimize: document.getElementById("portfolioOptimize"),
  portfolioSurface: document.getElementById("portfolioSurface"),
  tvOverviewWidget: document.getElementById("tvOverviewWidget"),
  tvOverviewFallback: document.getElementById("tvOverviewFallback"),
  tvHeatmapWidget: document.getElementById("tvHeatmapWidget"),
  tvHeatmapFallback: document.getElementById("tvHeatmapFallback"),
  symbolPickerModal: document.getElementById("symbolPickerModal"),
  symbolPickerClose: document.getElementById("symbolPickerClose"),
  symbolPickerSearch: document.getElementById("symbolPickerSearch"),
  symbolPickerTabs: document.getElementById("symbolPickerTabs"),
  symbolPickerCountry: document.getElementById("symbolPickerCountry"),
  symbolPickerSector: document.getElementById("symbolPickerSector"),
  symbolPickerSelected: document.getElementById("symbolPickerSelected"),
  symbolPickerList: document.getElementById("symbolPickerList"),
  symbolPickerClear: document.getElementById("symbolPickerClear"),
  symbolPickerApply: document.getElementById("symbolPickerApply"),
};

// Shared state
const state = {
  config: null,
  lastResponse: null,
  lastCollection: null,
  lastRequest: null,
  activeRequest: null,
  evidenceRaw: [],
  preflight: null,
  preflightTimer: null,
  pendingTimer: null,
  stageTimer: null,
  stageIndex: 0,
  startedAt: null,
  streamStartedAt: null,
  streamHasPartial: false,
  historyExpanded: false,
  dashboardLoaded: false,
  marketLoaded: false,
  dataHealthLoaded: false,
  dashboardHeatmapLoaded: false,
  tradingViewInitialized: false,
  dashboardNewsItems: [],
  dashboardNewsCategory: "all",
  activeDashboardTab: "market",
  lastBacktestRequest: null,
  lastQuantBacktestRequest: null,
  lastBacktestResult: null,
  lastFeatureResult: null,
  lastSignalResult: null,
  quantStrategiesLoaded: false,
  quantStrategyItems: [],
  activeStrategyId: "",
  symbolPickerType: "all",
  quantRunHistoryLoaded: false,
  lastCrossRunExportCleanupPreview: null,
};

const SYMBOL_CATALOG = [
  { symbol: "SPY", name: "SPDR S&P 500 ETF Trust", type: "etf", country: "US", sector: "macro", exchange: "NYSE Arca" },
  { symbol: "QQQ", name: "Invesco QQQ Trust", type: "etf", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "DIA", name: "SPDR Dow Jones Industrial Average ETF", type: "etf", country: "US", sector: "macro", exchange: "NYSE Arca" },
  { symbol: "IWM", name: "iShares Russell 2000 ETF", type: "etf", country: "US", sector: "macro", exchange: "NYSE Arca" },
  { symbol: "TLT", name: "iShares 20+ Year Treasury Bond ETF", type: "etf", country: "US", sector: "macro", exchange: "NASDAQ" },
  { symbol: "GLD", name: "SPDR Gold Shares", type: "etf", country: "US", sector: "macro", exchange: "NYSE Arca" },
  { symbol: "AAPL", name: "Apple Inc.", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "MSFT", name: "Microsoft Corporation", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "NVDA", name: "NVIDIA Corporation", type: "stock", country: "US", sector: "ai_semis", exchange: "NASDAQ" },
  { symbol: "TSLA", name: "Tesla, Inc.", type: "stock", country: "US", sector: "consumer", exchange: "NASDAQ" },
  { symbol: "GOOGL", name: "Alphabet Inc.", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "AMZN", name: "Amazon.com, Inc.", type: "stock", country: "US", sector: "consumer", exchange: "NASDAQ" },
  { symbol: "META", name: "Meta Platforms, Inc.", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "AMD", name: "Advanced Micro Devices, Inc.", type: "stock", country: "US", sector: "ai_semis", exchange: "NASDAQ" },
  { symbol: "AVGO", name: "Broadcom Inc.", type: "stock", country: "US", sector: "ai_semis", exchange: "NASDAQ" },
  { symbol: "MU", name: "Micron Technology, Inc.", type: "stock", country: "US", sector: "ai_semis", exchange: "NASDAQ" },
  { symbol: "PLTR", name: "Palantir Technologies Inc. Class A", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "CRCL", name: "Circle Internet Group, Inc. Class A", type: "stock", country: "US", sector: "financials", exchange: "NYSE" },
  { symbol: "IONQ", name: "IonQ, Inc.", type: "stock", country: "US", sector: "technology", exchange: "NYSE" },
  { symbol: "MSTR", name: "Strategy Inc. Class A", type: "stock", country: "US", sector: "technology", exchange: "NASDAQ" },
  { symbol: "JPM", name: "JPMorgan Chase & Co.", type: "stock", country: "US", sector: "financials", exchange: "NYSE" },
  { symbol: "BRK-B", name: "Berkshire Hathaway Inc. Class B", type: "stock", country: "US", sector: "financials", exchange: "NYSE" },
  { symbol: "005930", name: "Samsung Electronics Co., Ltd.", type: "stock", country: "KR", sector: "technology", exchange: "KRX" },
  { symbol: "000660", name: "SK hynix Inc.", type: "stock", country: "KR", sector: "ai_semis", exchange: "KRX" },
  { symbol: "BTC-USD", name: "Bitcoin USD", type: "crypto", country: "GLOBAL", sector: "crypto", exchange: "Crypto" },
  { symbol: "ETH-USD", name: "Ethereum USD", type: "crypto", country: "GLOBAL", sector: "crypto", exchange: "Crypto" },
  { symbol: "^GSPC", name: "S&P 500 Index", type: "index", country: "US", sector: "macro", exchange: "INDEX" },
  { symbol: "^IXIC", name: "NASDAQ Composite", type: "index", country: "US", sector: "technology", exchange: "INDEX" },
];

// ---------- Utilities ----------
const fmtDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
};

const escapeHtml = (s) => String(s ?? "")
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;");

const statusClass = (s) => ({ success: "success", partial: "partial", failed: "failed" }[s] || "muted");

const sourceStatusClass = (s) => {
  const key = (s || "").toLowerCase();
  if (["ok", "success"].includes(key)) return "ok";
  if (["failed", "error", "timeout"].includes(key)) return "fail";
  if (["empty", "entitlement_required", "credentials_missing", "rate_limited", "no_data_in_window", "provider_unavailable", "partial"].includes(key)) return "warn";
  return "muted";
};

const KNOWN_TICKERS = [
  "GOOGL", "SOXX", "AAPL", "MSFT", "NVDA", "TSLA", "GOOG", "AMZN",
  "META", "ASML", "AMAT", "KLAC", "INTC", "SPY", "QQQ", "XLK",
  "SMH", "TLT", "USO", "GLD", "JPM", "AMD", "GS",
  "IEF", "SHY", "AGG", "LQD", "HYG", "SLV", "DXY",
];
const TICKER_PREFIX_RE = new RegExp(`^(${KNOWN_TICKERS.join("|")})(?=$|[^A-Za-z0-9])`, "i");

function normalizeTickerToken(value) {
  return String(value || "")
    .trim()
    .replace(/^\$/, "")
    .toUpperCase();
}

function parseTickerInput(raw) {
  const seen = new Set();
  return String(raw || "")
    .split(/[\s,]+/)
    .map(normalizeTickerToken)
    .filter((ticker) => {
      if (!ticker || seen.has(ticker)) return false;
      seen.add(ticker);
      return true;
    });
}

function setBacktestUniverse(tickers) {
  const clean = [];
  const seen = new Set();
  (tickers || []).map(normalizeTickerToken).forEach((ticker) => {
    if (!ticker || seen.has(ticker)) return;
    seen.add(ticker);
    clean.push(ticker);
  });
  if (els.backtestTicker) els.backtestTicker.value = clean.join(",");
  renderBacktestUniverseChips();
}

function selectedBacktestUniverse() {
  return parseTickerInput(els.backtestTicker?.value || "");
}

function renderBacktestUniverseChips() {
  if (!els.backtestUniverseChips) return;
  const tickers = selectedBacktestUniverse();
  els.backtestUniverseChips.innerHTML = tickers.length
    ? tickers.map((ticker) => `
        <button type="button" data-universe-remove="${escapeHtml(ticker)}" title="${escapeHtml(ticker)} 제거">${escapeHtml(ticker)}</button>
      `).join("")
    : '<span>선택된 심볼 없음</span>';
  els.backtestUniverseChips.querySelectorAll("[data-universe-remove]").forEach((button) => {
    button.addEventListener("click", () => {
      setBacktestUniverse(selectedBacktestUniverse().filter((ticker) => ticker !== button.dataset.universeRemove));
    });
  });
}

function symbolPickerMatches(item, query, selectedType, country, sector) {
  if (!item) return false;
  if (selectedType !== "all" && item.type !== selectedType) return false;
  if (country !== "all" && item.country !== country) return false;
  if (sector !== "all" && item.sector !== sector) return false;
  if (!query) return true;
  const haystack = `${item.symbol} ${item.name} ${item.exchange} ${item.type} ${item.country}`.toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function renderSymbolPicker() {
  if (!els.symbolPickerList) return;
  const selected = new Set(selectedBacktestUniverse());
  const query = els.symbolPickerSearch?.value.trim() || "";
  const type = state.symbolPickerType || "all";
  const country = els.symbolPickerCountry?.value || "all";
  const sector = els.symbolPickerSector?.value || "all";
  const items = SYMBOL_CATALOG
    .filter((item) => symbolPickerMatches(item, query, type, country, sector))
    .sort((a, b) => Number(selected.has(b.symbol)) - Number(selected.has(a.symbol)) || a.symbol.localeCompare(b.symbol));

  if (els.symbolPickerSelected) {
    els.symbolPickerSelected.innerHTML = selected.size
      ? Array.from(selected).map((ticker) => `<span>${escapeHtml(ticker)}</span>`).join("")
      : '<span>백테스트에 사용할 심볼을 선택하세요.</span>';
  }
  els.symbolPickerList.innerHTML = items.length
    ? items.map((item) => {
        const isSelected = selected.has(item.symbol);
        return `
          <button type="button" class="symbol-picker-row${isSelected ? " selected" : ""}" data-symbol-toggle="${escapeHtml(item.symbol)}">
            <span class="symbol-picker-symbol">${escapeHtml(item.symbol)}</span>
            <span class="symbol-picker-name">${escapeHtml(item.name)}</span>
            <span class="symbol-picker-meta">${escapeHtml(item.type)} · ${escapeHtml(item.exchange)}</span>
          </button>
        `;
      }).join("")
    : '<div class="symbol-picker-empty">검색 조건과 일치하는 심볼이 없습니다.</div>';
}

function openSymbolPicker() {
  if (!els.symbolPickerModal) return;
  state.symbolPickerType = "all";
  els.symbolPickerTabs?.querySelectorAll("[data-symbol-type]").forEach((button) => {
    button.classList.toggle("active", button.dataset.symbolType === "all");
  });
  if (els.symbolPickerSearch) els.symbolPickerSearch.value = "";
  if (els.symbolPickerCountry) els.symbolPickerCountry.value = "all";
  if (els.symbolPickerSector) els.symbolPickerSector.value = "all";
  els.symbolPickerModal.classList.remove("hidden");
  renderSymbolPicker();
  window.setTimeout(() => els.symbolPickerSearch?.focus(), 0);
}

function closeSymbolPicker() {
  els.symbolPickerModal?.classList.add("hidden");
}

function toggleSymbolPickerItem(symbol) {
  const ticker = normalizeTickerToken(symbol);
  if (!ticker) return;
  const selected = selectedBacktestUniverse();
  if (selected.includes(ticker)) {
    setBacktestUniverse(selected.filter((item) => item !== ticker));
  } else {
    setBacktestUniverse([...selected, ticker]);
  }
  renderSymbolPicker();
}

function inferTickerFromQuestion(question) {
  const text = String(question || "").trimStart();
  if (!text) return null;

  // Marker-based extraction is intentionally permissive so users can type
  // "$BRK.B" or "BRK.B: ..." even when the symbol is not in the chip list.
  const marked = text.match(/^\$([A-Za-z][A-Za-z0-9]{0,9}(?:[.\-=][A-Za-z0-9]{1,8})?)(?=$|[^A-Za-z0-9])/);
  if (marked) return { ticker: normalizeTickerToken(marked[1]), source: "question_marker" };

  const colon = text.match(/^([A-Za-z][A-Za-z0-9]{0,9}(?:[.\-=][A-Za-z0-9]{1,8})?)\s*[:：]/);
  if (colon) return { ticker: normalizeTickerToken(colon[1]), source: "question_prefix" };

  // Plain leading words are restricted to known symbols to avoid treating
  // "What" or "AI" as a ticker.
  const known = text.match(TICKER_PREFIX_RE);
  if (known) return { ticker: normalizeTickerToken(known[1]), source: "known_prefix" };
  return null;
}

function normalizeResearchIntent({ tickerRaw, question, modeHint, compare }) {
  const cleanQuestion = String(question || "").trim();
  const mode = ["auto", "ticker", "topic"].includes(modeHint) ? modeHint : "auto";
  const typedTickers = parseTickerInput(tickerRaw);
  const inferred = (!typedTickers.length && !compare) ? inferTickerFromQuestion(cleanQuestion) : null;
  const tickers = typedTickers.length ? typedTickers : (inferred ? [inferred.ticker] : []);
  const ticker = tickers[0] || "";
  const intentKind = compare
    ? "compare"
    : mode === "ticker"
      ? "single_ticker_required"
      : mode === "topic"
        ? "topic"
        : ticker
          ? "auto_with_ticker_hint"
          : "auto_topic";

  return {
    ticker,
    tickers,
    compare: !!compare,
    mode_hint: mode,
    question: cleanQuestion,
    intent_kind: intentKind,
    extracted_ticker: inferred?.ticker || "",
    route_hint: compare ? "compare" : "universal",
  };
}

// ---------- Health ----------
async function checkHealth() {
  try {
    const res = await fetch(API.health);
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    els.healthPill.textContent = `api · v${data.version || ""}`;
    els.healthPill.classList.add("ok");
    els.healthPill.classList.remove("err");
  } catch (e) {
    els.healthPill.textContent = "api offline";
    els.healthPill.classList.add("err");
    els.healthPill.classList.remove("ok");
  }
}

// ---------- Preflight ----------
const PREFLIGHT_WARNING_ONLY = new Set([
  "HF_TOKEN", "FMP_API_KEY", "FMP_STOCK_NEWS",
  "SEC_FILINGS", "FRED_MACRO", "TRANSCRIPT_PROVIDER", "ALPHA_VANTAGE_NEWS",
  "QDRANT_COLLECTION_SCHEMA", "OPENBB_NEWS_RUNTIME", "OPENBB_AGENT_CONTRACT",
]);

function classifyCheck(check) {
  if (check.ok) return "ok";
  return PREFLIGHT_WARNING_ONLY.has(check.name) ? "warn" : "err";
}

function preflightStateLabel(level) {
  if (level === "ok") return "정상";
  if (level === "warn") return "경고";
  if (level === "err") return "치명";
  return "확인";
}

function summarizePreflight(report) {
  const checks = (report && report.checks) || [];
  let critical = 0;
  let warning = 0;
  for (const c of checks) {
    const state = classifyCheck(c);
    if (state === "err") critical += 1;
    else if (state === "warn") warning += 1;
  }
  if (!checks.length) return { level: "muted", label: "사전 점검: 알 수 없음" };
  if (critical > 0) return { level: "err", label: `사전 점검: 치명 ${critical}개` };
  if (warning > 0) return { level: "warn", label: `사전 점검: 경고 ${warning}개` };
  return { level: "ok", label: "사전 점검: 정상" };
}

function renderPreflightPill(report) {
  const s = summarizePreflight(report);
  const pill = els.preflightPill;
  pill.classList.remove("ok", "warn", "err");
  if (s.level !== "muted") pill.classList.add(s.level);
  els.preflightLabel.textContent = s.label;
}

function renderPreflightPanel(report) {
  const checks = (report && report.checks) || [];
  els.preflightChecks.innerHTML = "";
  checks.forEach((c) => {
    const level = classifyCheck(c);
    const li = document.createElement("li");
    li.className = level;
    li.innerHTML = `
      <span class="status-dot"></span>
      <div>
        <div class="check-name">${escapeHtml(c.name)}</div>
        <div class="check-detail">${escapeHtml(c.detail || "")}</div>
      </div>
      <span class="check-state">${preflightStateLabel(level)}</span>
    `;
    els.preflightChecks.appendChild(li);
  });
  const ts = report.checked_at || "—";
  const overall = report.passed ? "핵심 통과" : "핵심 실패";
  els.preflightSubtitle.textContent = `마지막 점검: ${ts} · ${overall}`;
}

async function loadPreflight(force = false) {
  try {
    const res = await fetch(force ? API.preflightForce : API.preflight);
    if (!res.ok) throw new Error(`bad status ${res.status}`);
    const report = await res.json();
    state.preflight = report;
    renderPreflightPill(report);
    if (!els.preflightPanel.classList.contains("hidden")) {
      renderPreflightPanel(report);
    }
    return report;
  } catch (e) {
    els.preflightPill.classList.remove("ok", "warn");
    els.preflightPill.classList.add("err");
    els.preflightLabel.textContent = "사전 점검: 오프라인";
    return null;
  }
}

async function loadRunbook() {
  try {
    const res = await fetch(API.runbookFailureModes);
    if (!res.ok) return;
    const data = await res.json();
    els.preflightRunbook.innerHTML = "";
    (data.modes || []).forEach((mode) => {
      const li = document.createElement("li");
      const rems = (mode.remediation || [])
        .map((r) => `<li>${escapeHtml(r)}</li>`)
        .join("");
      li.innerHTML = `
        <div class="rb-title">${escapeHtml(mode.code)} · ${escapeHtml(mode.label)}</div>
        <div class="rb-symptom">${escapeHtml(mode.symptom || "")}</div>
        <ul class="rb-remediation">${rems}</ul>
      `;
      els.preflightRunbook.appendChild(li);
    });
  } catch (e) {
    // Non-fatal: runbook is static content.
  }
}

function openPreflightPanel() {
  els.preflightPanel.classList.remove("hidden");
  if (state.preflight) renderPreflightPanel(state.preflight);
  else loadPreflight(false).then((r) => r && renderPreflightPanel(r));
}

function closePreflightPanel() {
  els.preflightPanel.classList.add("hidden");
}

// ---------- Qdrant admin panel ----------
async function openQdrantPanel() {
  if (!els.qdrantPanel) return;
  els.qdrantPanel.classList.remove("hidden");
  await loadQdrantInfo();
}

function closeQdrantPanel() {
  if (!els.qdrantPanel) return;
  els.qdrantPanel.classList.add("hidden");
  if (els.qdrantPurgeResult) els.qdrantPurgeResult.textContent = "";
}

function _fmtNumber(n) {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString();
}

async function loadQdrantInfo() {
  if (!els.qdrantStats) return;
  els.qdrantStats.innerHTML = "<span class='muted'>Loading…</span>";
  els.qdrantSubtitle.textContent = "컬렉션 상태를 로드 중…";
  try {
    const res = await fetch(API.qdrantInfo);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const info = await res.json();
    renderQdrantInfo(info);
  } catch (err) {
    els.qdrantStats.innerHTML = `<span class='error'>조회 실패: ${escapeHtml(String(err.message || err))}</span>`;
    els.qdrantSubtitle.textContent = "조회 실패";
  }
}

function renderQdrantInfo(info) {
  if (!els.qdrantStats) return;
  const name = info.collection || "—";
  if (!info.exists) {
    els.qdrantSubtitle.textContent = `컬렉션 "${name}" 가 아직 생성되지 않았습니다.`;
    els.qdrantStats.innerHTML = "<span class='muted'>아직 ingest된 문서가 없습니다. 분석 한 번 실행 후 다시 확인하세요.</span>";
    els.qdrantBreakdownList.innerHTML = "<li class='muted'>—</li>";
    return;
  }
  els.qdrantSubtitle.textContent = `컬렉션: ${name} · status: ${info.status || "—"}`;
  const rows = [
    ["Points", _fmtNumber(info.points_count)],
    ["Vectors", _fmtNumber(info.vectors_count)],
    ["Indexed", _fmtNumber(info.indexed_vectors_count)],
    ["Segments", _fmtNumber(info.segments_count)],
    ["Payload fields", (info.payload_fields && info.payload_fields.length) ? info.payload_fields.join(", ") : "—"],
  ];
  els.qdrantStats.innerHTML = rows
    .map(([k, v]) => `<div class='qdrant-stat'><span class='qdrant-stat-k'>${escapeHtml(k)}</span><span class='qdrant-stat-v'>${escapeHtml(String(v))}</span></div>`)
    .join("");

  const bd = info.ticker_breakdown || [];
  if (bd.length === 0) {
    els.qdrantBreakdownList.innerHTML = "<li class='muted'>티커 정보가 있는 문서가 없습니다.</li>";
  } else {
    els.qdrantBreakdownList.innerHTML = bd
      .slice(0, 50)
      .map(
        (row) => `<li><span class='qdrant-bd-ticker'>${escapeHtml(row.ticker)}</span><span class='qdrant-bd-count'>${_fmtNumber(row.count)}</span></li>`,
      )
      .join("");
  }
  els.qdrantBreakdownNote.textContent = info.ticker_breakdown_truncated
    ? "(첫 2000개까지 스캔, 상위 50개 표시)"
    : (bd.length > 50 ? "(상위 50개 표시)" : "");
}

// ---------- Quality / Evaluation dashboard ----------
async function openQualityPanel() {
  if (!els.qualityPanel) return;
  els.qualityPanel.classList.remove("hidden");
  await loadQualityDashboard();
}

function closeQualityPanel() {
  if (els.qualityPanel) els.qualityPanel.classList.add("hidden");
}

async function loadQualityDashboard() {
  if (!els.qualitySummary) return;
  els.qualitySummary.innerHTML = "<span class='muted'>Loading…</span>";
  els.qualitySubtitle.textContent = "평가 결과를 로드 중…";
  try {
    const res = await fetch(API.evalDashboard);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderQualityDashboard(data);
  } catch (err) {
    els.qualitySummary.innerHTML = `<span class='error'>조회 실패: ${escapeHtml(String(err.message || err))}</span>`;
    els.qualitySubtitle.textContent = "조회 실패";
  }
}

function renderQualityDashboard(data) {
  if (!data) return;
  const summary = data.summary || {};
  const hasAnything = data.has_report || data.has_results;
  if (!hasAnything) {
    els.qualitySubtitle.textContent = "평가 산출물이 없습니다. quality_review.py 실행 후 다시 확인하세요.";
  } else {
    const parts = [];
    if (data.results_path) parts.push(`results: ${data.results_path}`);
    if (data.report_path) parts.push(`report: ${data.report_path}`);
    els.qualitySubtitle.textContent = parts.join(" · ") || "—";
  }

  const sc = summary.status_counts || {};
  const total = summary.total || 0;
  const kpis = [
    ["Cases", total],
    ["Pass", sc.success || 0],
    ["Partial", sc.partial || 0],
    ["Failed", sc.failed || 0],
    ["Avg confidence", summary.avg_confidence ?? "—"],
    ["Avg purity", summary.avg_purity ?? "—"],
    ["Avg elapsed", summary.avg_elapsed_s != null ? `${summary.avg_elapsed_s}s` : "—"],
  ];
  els.qualitySummary.innerHTML = kpis
    .map(([k, v]) => `<div class='quality-kpi'><span class='quality-kpi-k'>${escapeHtml(k)}</span><span class='quality-kpi-v'>${escapeHtml(String(v))}</span></div>`)
    .join("");

  const cats = summary.categories || [];
  if (cats.length === 0) {
    els.qualityCategories.innerHTML = "<li class='muted'>카테고리 데이터 없음.</li>";
  } else {
    els.qualityCategories.innerHTML = cats
      .map((c) => {
        const passRate = c.count ? Math.round((c.pass / c.count) * 100) : 0;
        const conf = c.avg_confidence != null ? c.avg_confidence : "—";
        return `<li class='quality-category'>
          <div class='quality-category-top'>
            <span class='quality-category-name'>${escapeHtml(c.category)}</span>
            <span class='quality-category-count'>${c.count} cases · ${passRate}% pass</span>
          </div>
          <div class='quality-category-bar'>
            <div class='quality-bar-pass' style='width:${(c.pass / Math.max(c.count, 1)) * 100}%'></div>
            <div class='quality-bar-partial' style='width:${(c.partial / Math.max(c.count, 1)) * 100}%'></div>
            <div class='quality-bar-failed' style='width:${(c.failed / Math.max(c.count, 1)) * 100}%'></div>
          </div>
          <div class='quality-category-meta'>avg confidence: ${escapeHtml(String(conf))}</div>
        </li>`;
      })
      .join("");
  }

  const cases = data.cases || [];
  els.qualityCasesNote.textContent = cases.length ? `(최근 ${cases.length}건)` : "";
  if (cases.length === 0) {
    els.qualityCases.innerHTML = "<li class='muted'>실행된 케이스가 없습니다.</li>";
  } else {
    els.qualityCases.innerHTML = cases
      .slice()
      .reverse()
      .map((c) => {
        const statusClass = c.status === "success" ? "ok" : (c.status === "partial" ? "warn" : "err");
        return `<li class='quality-case'>
          <div class='quality-case-top'>
            <span class='quality-case-status ${statusClass}'>${escapeHtml(c.status || "—")}</span>
            <span class='quality-case-ticker'>${escapeHtml(c.ticker || "")}</span>
            <span class='quality-case-cat'>${escapeHtml(c.category || "")}</span>
            <span class='quality-case-meta'>conf ${escapeHtml(String(c.confidence ?? "—"))} · chunks ${escapeHtml(String(c.context_chunks ?? 0))} · purity ${escapeHtml(String(c.purity_ratio ?? "—"))}</span>
          </div>
          <div class='quality-case-desc'>${escapeHtml(c.desc || c.question || "")}</div>
          ${c.error ? `<div class='quality-case-error'>${escapeHtml(c.error)}</div>` : ""}
        </li>`;
      })
      .join("");
  }

  if (els.qualityReport) {
    els.qualityReport.textContent = data.report_markdown || "(latest_eval_report.md 를 찾을 수 없습니다)";
  }
}

async function runQdrantPurge(dryRun) {
  if (!els.qdrantPurgeResult) return;
  const days = els.qdrantPurgeDays.value.trim();
  const ticker = els.qdrantPurgeTicker.value.trim().toUpperCase();
  if (!days && !ticker) {
    els.qdrantPurgeResult.textContent = "나이(days) 또는 티커를 최소 하나 지정하세요.";
    els.qdrantPurgeResult.className = "qdrant-purge-result error";
    return;
  }
  if (!dryRun) {
    const confirmMsg = `정말 삭제하시겠습니까?\n${days ? "older_than_days=" + days + "일" : ""} ${ticker ? "ticker=" + ticker : ""}`.trim();
    if (!window.confirm(confirmMsg)) return;
  }
  const params = new URLSearchParams();
  if (days) params.set("older_than_days", days);
  if (ticker) params.set("ticker", ticker);
  if (dryRun) params.set("dry_run", "true");
  els.qdrantPurgeResult.className = "qdrant-purge-result muted";
  els.qdrantPurgeResult.textContent = dryRun ? "Dry run 실행 중…" : "Purge 실행 중…";
  try {
    const res = await fetch(`${API.qdrantPurge}?${params.toString()}`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.qdrantPurgeResult.className = "qdrant-purge-result ok";
    els.qdrantPurgeResult.textContent = dryRun
      ? `[dry run] scanned=${data.scanned} matched=${data.matched}. 실제 삭제 시 이만큼 제거됩니다.`
      : `✓ 삭제 완료 — scanned=${data.scanned}, matched=${data.matched}, deleted=${data.deleted}.`;
    if (!dryRun) {
      // Refresh stats after a real purge so the UI reflects the new state.
      await loadQdrantInfo();
    }
  } catch (err) {
    els.qdrantPurgeResult.className = "qdrant-purge-result error";
    els.qdrantPurgeResult.textContent = `실패: ${err.message || err}`;
  }
}

// ---------- Config / presets ----------
async function loadConfig() {
  try {
    const res = await fetch(API.config);
    if (!res.ok) return;
    state.config = await res.json();
    renderModelOptions(state.config.models || []);
    renderPresets(state.config.presets || []);
    applyLimits(state.config.limits || {});
  } catch (e) {
    console.warn("config fetch failed", e);
    renderModelOptions([]);
    renderPresets([]);
  }
}

const CLEAN_PRESETS = [
  { id: "risk", label: "단기 리스크", question: "현재 드러나는 주요 단기 리스크와 시장이 과소평가하는 하방 시나리오는 무엇인가요?" },
  { id: "catalyst", label: "성장 촉매", question: "향후 6~12개월 동안 가격을 움직일 핵심 상승 촉매와 검증 지표는 무엇인가요?" },
  { id: "thesis", label: "12개월 투자 가설", question: "최신 공개 정보와 정량 지표를 기준으로 12개월 투자 가설을 정리해주세요." },
  { id: "earnings", label: "실적 신호", question: "최근 실적과 가이던스에서 확인되는 매출, 마진, 비용 구조의 핵심 신호를 요약해주세요." },
  { id: "competitive", label: "경쟁 구도", question: "경쟁 구도가 어떻게 변하고 있고, 가격 결정력과 시장점유율에는 어떤 영향을 주나요?" },
];

function isReadablePreset(p) {
  const text = `${p?.label || ""} ${p?.question || ""}`;
  return /[가-힣A-Za-z]/.test(text) && !/[�]/.test(text);
}

function renderModelOptions(models) {
  if (!els.model) return;
  const current = els.model.value || "qwen";
  const rawOptions = Array.isArray(models) && models.length
    ? models.map((m) => (typeof m === "string" ? { id: m, label: m } : m))
    : [{ id: "qwen", label: "qwen2.5:7b (Ollama · 기본)" }];
  const options = rawOptions.filter((m) => m && m.id && (m.id === "qwen" || m.role === "fallback"));
  if (!options.length) options.push({ id: "qwen", label: "qwen2.5:7b (Ollama · 기본)" });
  els.model.innerHTML = "";
  options.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label || m.id;
      els.model.appendChild(opt);
    });
  els.model.value = Array.from(els.model.options).some((opt) => opt.value === current) ? current : "qwen";
}

function renderPresets(presets) {
  els.presetChips.innerHTML = "";
  const usable = Array.isArray(presets) && presets.length && presets.every(isReadablePreset)
    ? presets
    : CLEAN_PRESETS;
  usable.forEach((p) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = p.label;
    btn.title = p.question;
    btn.addEventListener("click", () => {
      els.question.value = p.question;
      els.question.focus();
      persistForm();
    });
    els.presetChips.appendChild(btn);
  });
}

function applyLimits(limits) {
  if (limits.lookback_days) {
    const { min, max, default: dflt } = limits.lookback_days;
    els.lookback.min = min;
    els.lookback.max = max;
    if (!els.lookback.dataset.dirty) els.lookback.value = dflt;
  }
  if (limits.top_k) {
    const { min, max, default: dflt } = limits.top_k;
    els.topk.min = min;
    els.topk.max = max;
    if (!els.topk.dataset.dirty) els.topk.value = dflt;
  }
  updateRangeLabels();
}

// ---------- Form ----------
function readForm() {
  const sources = Array.from(els.sourceInputs())
    .filter((i) => i.checked && !i.disabled)
    .map((i) => i.value);
  const raw = els.ticker.value.trim();
  const question = els.question.value.trim();
  const isCompare = !!(els.compareMode && els.compareMode.checked);
  const selectedMode = Array.from(els.researchModeInputs())
    .find((i) => i.checked)?.value || "auto";
  const intent = normalizeResearchIntent({
    tickerRaw: raw,
    question,
    modeHint: selectedMode,
    compare: isCompare,
  });
  return {
    ...intent,
    sources,
    lookback_days: parseInt(els.lookback.value, 10),
    top_k: parseInt(els.topk.value, 10),
    model: els.model.value,
  };
}

function persistForm() {
  try {
    localStorage.setItem(STORAGE.form, JSON.stringify(readForm()));
  } catch (e) { /* ignore */ }
}

function restoreForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE.form) || "null");
    if (!saved) return;
    if (saved.ticker) els.ticker.value = saved.ticker;
    if (saved.question) els.question.value = saved.question;
    if (Number.isFinite(saved.lookback_days)) els.lookback.value = saved.lookback_days;
    if (Number.isFinite(saved.top_k)) els.topk.value = saved.top_k;
    if (saved.model && Array.from(els.model.options).some((opt) => opt.value === saved.model)) {
      els.model.value = saved.model;
    }
    if (Array.isArray(saved.sources)) {
      els.sourceInputs().forEach((i) => {
        if (i.disabled) return;
        i.checked = saved.sources.includes(i.value);
      });
    }
    if (saved.compare && els.compareMode) {
      els.compareMode.checked = true;
    }
    if (saved.mode_hint) {
      els.researchModeInputs().forEach((i) => {
        i.checked = i.value === saved.mode_hint;
      });
    }
  } catch (e) { /* ignore */ }
  updateRangeLabels();
  if (typeof updateCompareModeUI === "function") updateCompareModeUI();
}

function updateRangeLabels() {
  els.lookbackValue.textContent = `${els.lookback.value}d`;
  els.topkValue.textContent = els.topk.value;
}

function setFormNotice(message, level = "info") {
  if (!els.formNotice) return;
  if (!message) {
    els.formNotice.classList.add("hidden");
    els.formNotice.textContent = "";
    els.formNotice.classList.remove("warning", "error", "info");
    return;
  }
  els.formNotice.textContent = message;
  els.formNotice.classList.remove("hidden", "warning", "error", "info");
  els.formNotice.classList.add(level);
}

function setText(selector, text) {
  const el = document.querySelector(selector);
  if (el) el.textContent = text;
}

function setDashboardTab(tab = "market") {
  const active = tab === "quant" ? "quant" : "market";
  state.activeDashboardTab = active;
  if (els.homeSurfaceGrid) {
    els.homeSurfaceGrid.dataset.dashboardTab = active;
  }
  const buttons = [
    { el: els.marketDashboardTab, tab: "market" },
    { el: els.quantLabTab, tab: "quant" },
  ];
  buttons.forEach(({ el, tab: buttonTab }) => {
    if (!el) return;
    const isActive = buttonTab === active;
    el.classList.toggle("active", isActive);
    el.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  const homeTitle = document.querySelector(".home-hero h2");
  const homeCopy = document.querySelector(".home-hero p:not(.eyebrow)");
  if (active === "quant") {
    if (homeTitle) homeTitle.textContent = "퀀트 랩";
    if (homeCopy) homeCopy.textContent = "저장 가격 기반 리스크, 전략 검증, 포트폴리오 배분을 같은 조건으로 점검합니다.";
    loadQuantRunHistory(false);
    loadQuantStrategies(false);
  } else {
    if (homeTitle) homeTitle.textContent = "시장 대시보드";
    if (homeCopy) homeCopy.textContent = "티커를 입력하면 종목 분석으로, 비워두고 질문만 입력하면 금리·신용·FX·원자재·테마 topic 분석으로 라우팅합니다.";
  }
}

function applyUrlUiMode() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("focus") !== "heatmap") return;
  document.body.classList.add("heatmap-focus-mode");
  setDashboardTab("market");
}

function normalizeStaticLabels() {
  document.title = "FinGPT Local Research Assistant";
  if (els.tickerHint) els.tickerHint.textContent = "ticker 없이 질의 가능, ticker는 참고 힌트";
  if (els.ticker) els.ticker.placeholder = "선택: TLT, GLD, BTC-USD";
  if (els.question) els.question.placeholder = "예: 현재 시장이 무시하는 리스크는 무엇인가요?";
  const modeLabels = {
    auto: "자동",
    ticker: "종목",
    topic: "주제",
  };
  els.researchModeInputs().forEach((input) => {
    const span = input.parentElement?.querySelector("span");
    if (span && modeLabels[input.value]) span.textContent = modeLabels[input.value];
  });
  const qHint = document.querySelector('label[for="question"] .hint');
  if (qHint) qHint.textContent = "자유 질문 또는 프리셋 선택";
  const evidenceSearch = document.getElementById("evidenceSearch");
  if (evidenceSearch) evidenceSearch.placeholder = "검색: 제목, 내용, source, doc_id";
  setDashboardTab(state.activeDashboardTab || "market");
  applyUrlUiMode();
  const homeStatus = document.querySelectorAll(".home-status span");
  if (homeStatus[0]) homeStatus[0].textContent = "OpenBB/Yahoo/FRED/SEC 중심";
  if (homeStatus[1]) homeStatus[1].textContent = "qwen2.5:7b 로컬 추론";
  setText(".home-chart-card .home-card-head h3", "TradingView 단일 차트");
  setText(".home-heatmap-card .home-card-head h3", "미국 주식 5분봉 히트맵");
  setText(".home-market-panel .home-card-head h3", "내부 시장 스냅샷");
  setText(".data-mart-card .home-card-head h3", "데이터 마트 상태");
  setText(".asset-detail-card .home-card-head h3", "자산 상세");
  setText(".backtest-card .home-card-head h3", "백테스트");
  setText(".portfolio-card .home-card-head h3", "포트폴리오");
  setText(".home-news-card .home-card-head h3", "주요 뉴스");
  const runMeta = document.querySelector(".meta-row");
  if (runMeta) runMeta.innerHTML = '<span class="kbd">Ctrl</span> + <span class="kbd">Enter</span> 실행';
}

function showHome() {
  state.lastResponse = null;
  state.lastCollection = null;
  state.lastRequest = null;
  setExportAvailability(false);
  setFormNotice("");
  if (els.compareView) els.compareView.classList.add("hidden");
  els.loadingState.classList.add("hidden");
  els.resultView.classList.add("hidden");
  els.emptyState.classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
  initializeTradingViewDashboard(false);
  loadDashboardEquityHeatmap(false);
  loadDashboardMarket(false);
  loadDashboardNews(false);
}

function showTvFallback(el, message) {
  if (!el) return;
  if (el.dataset?.preserveContent === "true") {
    const messageEl = el.querySelector(".tv-fallback-message");
    if (messageEl) messageEl.textContent = message;
  } else {
    el.textContent = message;
  }
  el.classList.remove("hidden");
}

function hideTvFallback(el) {
  if (el) el.classList.add("hidden");
}

function tradingViewEmbedUrl(scriptSrc, config) {
  let widget = "";
  if (scriptSrc.includes("stock-heatmap")) widget = "stock-heatmap";
  else if (scriptSrc.includes("advanced-chart")) widget = "advanced-chart";
  if (!widget) return "";
  const locale = config.locale || "kr";
  const payload = encodeURIComponent(JSON.stringify(config));
  return `https://s.tradingview.com/embed-widget/${widget}/?locale=${encodeURIComponent(locale)}#${payload}`;
}

function mountTradingViewIframe(container, scriptSrc, config, label) {
  const url = tradingViewEmbedUrl(scriptSrc, config);
  if (!url) return false;
  container.innerHTML = "";
  const iframe = document.createElement("iframe");
  iframe.title = label;
  iframe.src = url;
  iframe.loading = "eager";
  iframe.referrerPolicy = "origin";
  iframe.allow = "clipboard-write; encrypted-media; fullscreen";
  iframe.setAttribute("allowfullscreen", "true");
  iframe.style.width = "100%";
  iframe.style.height = "100%";
  iframe.style.border = "0";
  container.appendChild(iframe);
  return true;
}

function mountTradingViewWidget(container, fallback, scriptSrc, config, label) {
  if (!container) return;
  container.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
  container.dataset.tvStatus = "loading";
  hideTvFallback(fallback);
  const script = document.createElement("script");
  script.type = "text/javascript";
  script.async = true;
  script.src = scriptSrc;
  script.textContent = JSON.stringify(config);
  script.onerror = () => {
    const iframeMounted = mountTradingViewIframe(container, scriptSrc, config, label);
    container.dataset.tvStatus = iframeMounted ? "iframe-fallback" : "failed";
    showTvFallback(fallback, iframeMounted
      ? `${label} 스크립트가 차단되어 직접 iframe 경로로 전환했습니다.`
      : `${label} 로드에 실패했습니다. 아래 내부 시장 스냅샷을 기준으로 확인하세요.`);
  };
  container.appendChild(script);

  let checks = 0;
  const verify = () => {
    const frame = container.querySelector("iframe");
    const frameSrc = frame?.getAttribute("src") || "";
    if (frame && frameSrc && frameSrc !== "about:blank") {
      hideTvFallback(fallback);
      container.dataset.tvStatus = "ready";
      return;
    }
    checks += 1;
    if (checks === 4) {
      const iframeMounted = mountTradingViewIframe(container, scriptSrc, config, label);
      if (iframeMounted) {
        container.dataset.tvStatus = "iframe-fallback";
        showTvFallback(fallback, `${label} 로딩이 지연되어 직접 iframe 경로로 재시도했습니다.`);
      }
    }
    if (checks >= 8) {
      container.dataset.tvStatus = "degraded";
      showTvFallback(fallback, `${label} 위젯이 아직 응답하지 않습니다. 네트워크 또는 외부 스크립트 차단 시 내부 시장 스냅샷을 사용하세요.`);
      return;
    }
    window.setTimeout(verify, 1000);
  };
  window.setTimeout(verify, 1200);
}

function initializeTradingViewDashboard(force = false) {
  if (state.tradingViewInitialized && !force) return;
  state.tradingViewInitialized = true;
  mountTradingViewWidget(
    els.tvOverviewWidget,
    els.tvOverviewFallback,
    "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js",
    {
      autosize: true,
      symbol: "AMEX:SPY",
      interval: "D",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "kr",
      backgroundColor: "rgba(15, 23, 42, 1)",
      gridColor: "rgba(51, 65, 85, 0.35)",
      hide_top_toolbar: false,
      allow_symbol_change: true,
      save_image: false,
      calendar: false,
      height: "420",
      width: "100%",
      support_host: "https://www.tradingview.com",
    },
    "TradingView 단일 차트"
  );
  mountTradingViewWidget(
    els.tvHeatmapWidget,
    els.tvHeatmapFallback,
    "https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js",
    {
      exchanges: [],
      dataSource: "SPX500",
      grouping: "sector",
      blockSize: "market_cap_basic",
      blockColor: "change",
      locale: "kr",
      symbolUrl: "",
      colorTheme: "dark",
      hasTopBar: false,
      isDataSetEnabled: false,
      isZoomEnabled: true,
      hasSymbolTooltip: true,
      isMonoSize: false,
      width: "100%",
      height: "100%",
      support_host: "https://www.tradingview.com",
    },
    "TradingView 주식 히트맵"
  );
}

function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function heatColor(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "rgb(55, 65, 81)";
  const intensity = Math.min(Math.abs(n) / 3.0, 1);
  if (Math.abs(n) < 0.08) return "rgb(64, 70, 82)";
  if (n > 0) {
    const r = Math.round(28 + intensity * 20);
    const g = Math.round(116 + intensity * 86);
    const b = Math.round(65 + intensity * 44);
    return `rgb(${r}, ${g}, ${b})`;
  }
  const r = Math.round(116 + intensity * 112);
  const g = Math.round(58 - intensity * 8);
  const b = Math.round(70 - intensity * 16);
  return `rgb(${r}, ${g}, ${b})`;
}

function weightedSectorChange(items) {
  let totalWeight = 0;
  let weighted = 0;
  items.forEach((item) => {
    const change = Number(item.change_pct);
    const weight = Math.max(0.2, Number(item.weight) || 1);
    if (!Number.isFinite(change)) return;
    totalWeight += weight;
    weighted += change * weight;
  });
  return totalWeight ? weighted / totalWeight : null;
}

function sectorBreadth(items) {
  const usable = Array.isArray(items) ? items : [];
  const up = usable.filter((item) => Number(item.change_pct) >= 0).length;
  const down = usable.filter((item) => Number(item.change_pct) < 0).length;
  return { up, down, total: usable.length };
}

function heatmapWeight(item) {
  const weight = Number(item?.weight);
  return Number.isFinite(weight) && weight > 0 ? Math.max(weight, 0.2) : 1;
}

function heatmapLayoutWeight(item) {
  return Math.pow(Math.max(heatmapWeight(item), 0.45), 0.82);
}

function heatmapTicker(item) {
  return String(item?.symbol || "").trim().toUpperCase();
}

function fallbackHeatmapClassification(item) {
  const rawSector = String(item?.sector || "").toUpperCase();
  const rawIndustry = String(item?.industry || "").toUpperCase();
  if (HEATMAP_SECTOR_ORDER.includes(rawSector)) {
    return { sector: rawSector, industry: rawIndustry || rawSector };
  }
  if (rawSector.includes("TECH") || rawSector.includes("전자") || rawSector.includes("테크")) {
    return { sector: "TECHNOLOGY", industry: rawIndustry || "INFORMATION TECHNOLOGY" };
  }
  if (rawSector.includes("FIN") || rawSector.includes("금융")) {
    return { sector: "FINANCIAL", industry: rawIndustry || "FINANCIAL SERVICES" };
  }
  if (rawSector.includes("HEALTH") || rawSector.includes("의료") || rawSector.includes("헬스")) {
    return { sector: "HEALTHCARE", industry: rawIndustry || "HEALTHCARE" };
  }
  if (rawSector.includes("ENERGY") || rawSector.includes("에너지")) {
    return { sector: "ENERGY", industry: rawIndustry || "ENERGY" };
  }
  if (rawSector.includes("INDUSTR") || rawSector.includes("제조")) {
    return { sector: "INDUSTRIALS", industry: rawIndustry || "INDUSTRIALS" };
  }
  if (rawSector.includes("CONSUMER") || rawSector.includes("소비")) {
    return { sector: "CONSUMER CYCLICAL", industry: rawIndustry || "CONSUMER SERVICES" };
  }
  return { sector: "OTHER", industry: rawIndustry || (item?.sector ? String(item.sector).toUpperCase() : "UNCATEGORIZED") };
}

function heatmapProfile(item) {
  const backendProfile = fallbackHeatmapClassification(item);
  const staticProfile = HEATMAP_CLASSIFICATION[heatmapTicker(item)];
  if (HEATMAP_SECTOR_ORDER.includes(backendProfile.sector) && item?.industry) return backendProfile;
  return staticProfile || backendProfile;
}

function heatmapSectorRank(sector) {
  const idx = HEATMAP_SECTOR_ORDER.indexOf(sector);
  return idx >= 0 ? idx : HEATMAP_SECTOR_ORDER.length;
}

function heatmapRectStyle(rect) {
  return [
    `left:${Math.max(0, rect.x).toFixed(4)}%`,
    `top:${Math.max(0, rect.y).toFixed(4)}%`,
    `width:${Math.max(0, rect.w).toFixed(4)}%`,
    `height:${Math.max(0, rect.h).toFixed(4)}%`,
  ].join("; ");
}

function treemapWorst(row, side) {
  if (!row.length || side <= 0) return Number.POSITIVE_INFINITY;
  const areas = row.map((entry) => Math.max(0.0001, entry.area));
  const sum = areas.reduce((total, area) => total + area, 0);
  const min = Math.min(...areas);
  const max = Math.max(...areas);
  const sideSq = side * side;
  return Math.max((sideSq * max) / (sum * sum), (sum * sum) / (sideSq * min));
}

function layoutTreemapRow(row, rect, output) {
  const rowArea = row.reduce((sum, entry) => sum + entry.area, 0);
  if (rowArea <= 0 || rect.w <= 0 || rect.h <= 0) return rect;
  if (rect.w >= rect.h) {
    const rowHeight = Math.min(rect.h, rowArea / rect.w);
    let x = rect.x;
    row.forEach((entry, index) => {
      const width = index === row.length - 1
        ? rect.x + rect.w - x
        : Math.min(rect.x + rect.w - x, entry.area / rowHeight);
      output.push({ item: entry.item, x, y: rect.y, w: width, h: rowHeight });
      x += width;
    });
    return { x: rect.x, y: rect.y + rowHeight, w: rect.w, h: Math.max(0, rect.h - rowHeight) };
  }
  const columnWidth = Math.min(rect.w, rowArea / rect.h);
  let y = rect.y;
  row.forEach((entry, index) => {
    const height = index === row.length - 1
      ? rect.y + rect.h - y
      : Math.min(rect.y + rect.h - y, entry.area / columnWidth);
    output.push({ item: entry.item, x: rect.x, y, w: columnWidth, h: height });
    y += height;
  });
  return { x: rect.x + columnWidth, y: rect.y, w: Math.max(0, rect.w - columnWidth), h: rect.h };
}

function squarifyTreemap(entries, rect, valueFn) {
  const totalValue = entries.reduce((sum, entry) => {
    const value = Number(valueFn(entry));
    return sum + (Number.isFinite(value) && value > 0 ? value : 0);
  }, 0);
  if (!entries.length || totalValue <= 0 || rect.w <= 0 || rect.h <= 0) return [];
  const areaScale = (rect.w * rect.h) / totalValue;
  const queue = entries
    .map((entry) => {
      const value = Math.max(0.0001, Number(valueFn(entry)) || 0.0001);
      return { item: entry, area: value * areaScale };
    })
    .sort((a, b) => b.area - a.area);
  const output = [];
  let row = [];
  let remaining = { ...rect };
  while (queue.length) {
    const next = queue[0];
    const side = Math.min(remaining.w, remaining.h);
    if (!row.length || treemapWorst([...row, next], side) <= treemapWorst(row, side)) {
      row.push(next);
      queue.shift();
    } else {
      remaining = layoutTreemapRow(row, remaining, output);
      row = [];
    }
  }
  if (row.length) layoutTreemapRow(row, remaining, output);
  return output;
}

function squarifyTreemapPercent(entries, aspectRatio, valueFn) {
  const aspect = Math.min(Math.max(Number(aspectRatio) || 1, 0.2), 6);
  const layoutRect = aspect >= 1
    ? { x: 0, y: 0, w: 100 * aspect, h: 100 }
    : { x: 0, y: 0, w: 100, h: 100 / aspect };
  return squarifyTreemap(entries, layoutRect, valueFn).map(({ item, x, y, w, h }) => ({
    item,
    x: (x / layoutRect.w) * 100,
    y: (y / layoutRect.h) * 100,
    w: (w / layoutRect.w) * 100,
    h: (h / layoutRect.h) * 100,
  }));
}

function heatmapCanvasAspect() {
  const width = Number(els.homeHeatmap?.clientWidth || 0);
  const height = Number(els.homeHeatmap?.clientHeight || 0);
  if (width > 0 && height > 0) return width / height;
  return 1.85;
}

function heatmapTileSize(rect, sectorRect, industryRect) {
  const globalW = (sectorRect.w * industryRect.w * rect.w) / 10000;
  const globalH = (sectorRect.h * industryRect.h * rect.h) / 10000;
  const area = globalW * globalH;
  if (globalW >= 10 && globalH >= 15 && area >= 180) return "mega";
  if (globalW >= 7 && globalH >= 10 && area >= 80) return "xl";
  if (globalW >= 4.2 && globalH >= 6 && area >= 34) return "lg";
  if (globalW >= 2.6 && globalH >= 4 && area >= 14) return "md";
  if (globalW >= 1.6 && globalH >= 2.5 && area >= 5) return "sm";
  return "xs";
}

function fmtHeatmapAsOf(value) {
  if (!value) return "기준시각 미확인";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "America/New_York",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch (_) {
    return String(value);
  }
}

const FRESHNESS_LABELS = {
  fresh: "정상",
  delayed: "지연",
  stale: "지연 초과",
  stale_prior_close: "전일 기준",
  closed: "장마감",
  unknown: "미확인",
};

const HEATMAP_SECTOR_ORDER = [
  "TECHNOLOGY",
  "COMMUNICATION SERVICES",
  "CONSUMER CYCLICAL",
  "CONSUMER DEFENSIVE",
  "FINANCIAL",
  "HEALTHCARE",
  "INDUSTRIALS",
  "ENERGY",
  "UTILITIES",
  "REAL ESTATE",
  "BASIC MATERIALS",
  "OTHER",
];

const HEATMAP_SECTOR_ZONES = {
  TECHNOLOGY: { x: 0, y: 0, w: 45, h: 70 },
  FINANCIAL: { x: 0, y: 70, w: 45, h: 30 },
  "CONSUMER CYCLICAL": { x: 45, y: 0, w: 35, h: 30 },
  "COMMUNICATION SERVICES": { x: 45, y: 30, w: 35, h: 38 },
  HEALTHCARE: { x: 45, y: 68, w: 35, h: 32 },
  "CONSUMER DEFENSIVE": { x: 80, y: 0, w: 20, h: 30 },
  INDUSTRIALS: { x: 80, y: 30, w: 20, h: 31 },
  "REAL ESTATE": { x: 80, y: 61, w: 10, h: 18 },
  UTILITIES: { x: 90, y: 61, w: 10, h: 18 },
  ENERGY: { x: 80, y: 79, w: 12, h: 21 },
  "BASIC MATERIALS": { x: 92, y: 79, w: 8, h: 21 },
  OTHER: { x: 92, y: 61, w: 8, h: 18 },
};

const HEATMAP_DISPLAY_MAX = 96;
const HEATMAP_DISPLAY_MIN = 24;

const HEATMAP_CLASSIFICATION = {
  MSFT: { sector: "TECHNOLOGY", industry: "SOFTWARE - INFRASTRUCTURE" },
  ORCL: { sector: "TECHNOLOGY", industry: "SOFTWARE - INFRASTRUCTURE" },
  CRM: { sector: "TECHNOLOGY", industry: "SOFTWARE - APPLICATION" },
  AAPL: { sector: "TECHNOLOGY", industry: "CONSUMER ELECTRONICS" },
  NVDA: { sector: "TECHNOLOGY", industry: "SEMICONDUCTORS" },
  AVGO: { sector: "TECHNOLOGY", industry: "SEMICONDUCTORS" },
  AMD: { sector: "TECHNOLOGY", industry: "SEMICONDUCTORS" },
  MU: { sector: "TECHNOLOGY", industry: "SEMICONDUCTORS" },
  QCOM: { sector: "TECHNOLOGY", industry: "SEMICONDUCTORS" },
  CSCO: { sector: "TECHNOLOGY", industry: "COMMUNICATION EQUIPMENT" },
  GOOGL: { sector: "COMMUNICATION SERVICES", industry: "INTERNET CONTENT & INFORMATION" },
  META: { sector: "COMMUNICATION SERVICES", industry: "INTERNET CONTENT & INFORMATION" },
  NFLX: { sector: "COMMUNICATION SERVICES", industry: "ENTERTAINMENT" },
  AMZN: { sector: "CONSUMER CYCLICAL", industry: "INTERNET RETAIL" },
  TSLA: { sector: "CONSUMER CYCLICAL", industry: "AUTO MANUFACTURERS" },
  HD: { sector: "CONSUMER CYCLICAL", industry: "HOME IMPROVEMENT" },
  MCD: { sector: "CONSUMER CYCLICAL", industry: "RESTAURANTS" },
  BKNG: { sector: "CONSUMER CYCLICAL", industry: "TRAVEL SERVICES" },
  WMT: { sector: "CONSUMER DEFENSIVE", industry: "DISCOUNT STORES" },
  COST: { sector: "CONSUMER DEFENSIVE", industry: "DISCOUNT STORES" },
  PG: { sector: "CONSUMER DEFENSIVE", industry: "HOUSEHOLD & PERSONAL PRODUCTS" },
  KO: { sector: "CONSUMER DEFENSIVE", industry: "BEVERAGES - NON-ALCOHOLIC" },
  PEP: { sector: "CONSUMER DEFENSIVE", industry: "BEVERAGES - NON-ALCOHOLIC" },
  "BRK-B": { sector: "FINANCIAL", industry: "INSURANCE - DIVERSIFIED" },
  JPM: { sector: "FINANCIAL", industry: "BANKS - DIVERSIFIED" },
  BAC: { sector: "FINANCIAL", industry: "BANKS - DIVERSIFIED" },
  V: { sector: "FINANCIAL", industry: "CREDIT SERVICES" },
  MA: { sector: "FINANCIAL", industry: "CREDIT SERVICES" },
  LLY: { sector: "HEALTHCARE", industry: "DRUG MANUFACTURERS - GENERAL" },
  JNJ: { sector: "HEALTHCARE", industry: "DRUG MANUFACTURERS - GENERAL" },
  ABBV: { sector: "HEALTHCARE", industry: "DRUG MANUFACTURERS - GENERAL" },
  UNH: { sector: "HEALTHCARE", industry: "HEALTHCARE PLANS" },
  XOM: { sector: "ENERGY", industry: "OIL & GAS INTEGRATED" },
  CVX: { sector: "ENERGY", industry: "OIL & GAS INTEGRATED" },
  CAT: { sector: "INDUSTRIALS", industry: "FARM & HEAVY CONSTRUCTION" },
  GE: { sector: "INDUSTRIALS", industry: "AEROSPACE & DEFENSE" },
  RTX: { sector: "INDUSTRIALS", industry: "AEROSPACE & DEFENSE" },
};

function isDecisionUsableMarketItem(item) {
  if (!item) return false;
  if (item.is_decision_usable === false) return false;
  const status = item.freshness_status || "unknown";
  return item.status === "ok" && ["fresh", "delayed", "closed"].includes(status);
}

function renderHomeHeatmap(items, meta = {}) {
  if (!els.homeHeatmap) return;
  const usable = Array.isArray(items) ? items.filter(isDecisionUsableMarketItem) : [];
  if (!usable.length) {
    els.homeHeatmap.classList.remove("finviz-treemap");
    els.homeHeatmap.innerHTML = `
      <div class="home-news-empty">
        장중 최신/지연 intraday 데이터가 없어 히트맵을 숨겼습니다.<br>
        전일 기준 데이터는 의사결정용으로 표시하지 않습니다.
      </div>
    `;
    if (els.homeHeatmapMeta) {
      const stale = Number(meta.stale_or_unavailable_count || 0);
      els.homeHeatmapMeta.textContent = stale
        ? `${stale}개 종목이 stale 또는 unavailable 상태입니다. 새로고침으로 5분봉 데이터를 다시 확인하세요.`
        : "intraday 가격 데이터를 확인하지 못했습니다.";
    }
    return;
  }
  const displayTarget = Math.max(
    HEATMAP_DISPLAY_MIN,
    Math.min(HEATMAP_DISPLAY_MAX, Math.ceil(usable.length / 2)),
  );
  const displayItems = usable
    .slice()
    .sort((a, b) => {
      const weightDiff = heatmapWeight(b) - heatmapWeight(a);
      if (weightDiff) return weightDiff;
      return Math.abs(Number(b.change_pct || 0)) - Math.abs(Number(a.change_pct || 0));
    })
    .slice(0, displayTarget);
  const counts = meta.freshness_counts || {};
  const staleTotal = (counts.stale_prior_close || 0) + (counts.stale || 0) + (counts.unknown || 0);
  const latest = meta.latest_as_of ? fmtHeatmapAsOf(meta.latest_as_of) : "미확인";
  if (els.homeHeatmapMeta) {
    els.homeHeatmapMeta.innerHTML = `
      <span>최신 기준시각: ${escapeHtml(latest)} ET</span>
      <span>${escapeHtml(meta.interval || "5m")} intraday</span>
      <span>${escapeHtml(meta.provider || "yfinance")}</span>
      <span>표시 ${escapeHtml(_fmtNumber(displayItems.length))}/${escapeHtml(_fmtNumber(usable.length))}</span>
      ${staleTotal ? `<strong class="stale">제외: ${staleTotal}개 stale</strong>` : '<strong>신선도 정상</strong>'}
    `;
  }
  const profiledItems = displayItems.map((item) => ({ ...item, heatmap_profile: heatmapProfile(item) }));
  const bySector = new Map();
  profiledItems.forEach((item) => {
    const key = item.heatmap_profile.sector || "OTHER";
    if (!bySector.has(key)) bySector.set(key, []);
    bySector.get(key).push(item);
  });
  const sectors = Array.from(bySector.entries())
    .map(([sector, sectorItems]) => [sector, sectorItems.sort((a, b) => (Number(b.weight) || 0) - (Number(a.weight) || 0))])
    .sort((a, b) => {
      const rankDiff = heatmapSectorRank(a[0]) - heatmapSectorRank(b[0]);
      if (rankDiff) return rankDiff;
      return b[1].reduce((sum, row) => sum + heatmapWeight(row), 0) - a[1].reduce((sum, row) => sum + heatmapWeight(row), 0);
    });
  els.homeHeatmap.classList.add("finviz-treemap");
  const canvasAspect = heatmapCanvasAspect();
  const sectorMarkup = sectors.map(([sector, sectorItems]) => {
    const sectorRect = HEATMAP_SECTOR_ZONES[sector] || HEATMAP_SECTOR_ZONES.OTHER;
    const sectorAspect = Math.max(0.2, (sectorRect.w * canvasAspect) / Math.max(sectorRect.h, 1));
    const sectorChange = weightedSectorChange(sectorItems);
    const sectorCls = Number.isFinite(Number(sectorChange)) ? (Number(sectorChange) >= 0 ? "up" : "down") : "muted";
    const sectorChangeText = Number.isFinite(Number(sectorChange)) ? fmtPct(sectorChange) : "-";
    const breadth = sectorBreadth(sectorItems);
    const itemRects = squarifyTreemapPercent(sectorItems, sectorAspect, heatmapLayoutWeight);
    return `
    <section class="finviz-sector stock-heatmap-sector ${sectorCls}" style="${heatmapRectStyle(sectorRect)}">
      <div class="finviz-sector-title stock-sector-title">
        <div>
          <strong>${escapeHtml(sector)}</strong>
          <small>${breadth.up} 상승 · ${breadth.down} 하락</small>
        </div>
        <span class="${sectorCls}">${escapeHtml(sectorChangeText)}</span>
      </div>
      <div class="finviz-sector-body finviz-sector-tiles">
        ${itemRects.map(({ item, ...tileRect }) => {
          const change = item.change_pct;
          const cls = Number(change) >= 0 ? "up" : "down";
          const freshness = item.freshness_status || "unknown";
          const tileSize = heatmapTileSize(tileRect, sectorRect, { x: 0, y: 0, w: 100, h: 100 });
          const industry = item.heatmap_profile?.industry || item.industry || "";
          const title = `${item.symbol} ${item.label || ""} ${fmtPct(change)} · ${industry} · ${fmtHeatmapAsOf(item.as_of)} ET · ${FRESHNESS_LABELS[freshness] || freshness}`;
          return `
            <article class="finviz-heatmap-tile stock-heatmap-tile ${cls} ${freshness} size-${tileSize}" style="${heatmapRectStyle(tileRect)}; --heat-bg:${heatColor(change)}" title="${escapeHtml(title)}">
              <div class="stock-heatmap-main">
                <span class="stock-heatmap-symbol">${escapeHtml(item.symbol || "")}</span>
                <span class="stock-heatmap-change">${escapeHtml(fmtPct(change))}</span>
              </div>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
  }).join("");
  els.homeHeatmap.innerHTML = `
    ${sectorMarkup}
    <div class="finviz-legend" aria-label="Heatmap return legend">
      <span class="legend-box legend-down-3">-3%</span>
      <span class="legend-box legend-down-2">-2%</span>
      <span class="legend-box legend-down-1">-1%</span>
      <span class="legend-box legend-flat">0%</span>
      <span class="legend-box legend-up-1">+1%</span>
      <span class="legend-box legend-up-2">+2%</span>
      <span class="legend-box legend-up-3">+3%</span>
    </div>
  `;
}

async function loadDashboardEquityHeatmap(force = false) {
  if (!els.homeHeatmap || (state.dashboardHeatmapLoaded && !force)) return;
  els.homeHeatmap.classList.remove("finviz-treemap");
  els.homeHeatmap.innerHTML = '<div class="home-news-empty">intraday 히트맵 데이터를 불러오는 중입니다.</div>';
  if (els.homeHeatmapMeta) els.homeHeatmapMeta.textContent = "Yahoo/yfinance 5분봉 최신 가격을 확인하는 중입니다.";
  if (els.homeHeatmapRefresh) {
    els.homeHeatmapRefresh.disabled = true;
    els.homeHeatmapRefresh.textContent = force ? "새로고침 중" : "불러오는 중";
  }
  try {
    const url = force ? `${API.dashboardEquityHeatmap}?force=true` : API.dashboardEquityHeatmap;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    renderHomeHeatmap(items, data);
    state.dashboardHeatmapLoaded = true;
  } catch (err) {
    els.homeHeatmap.innerHTML = `<div class="home-news-empty">intraday 히트맵 로드 실패: ${escapeHtml(err.message || err)}</div>`;
    if (els.homeHeatmapMeta) els.homeHeatmapMeta.textContent = "히트맵 데이터 로드 실패";
  } finally {
    if (els.homeHeatmapRefresh) {
      els.homeHeatmapRefresh.disabled = false;
      els.homeHeatmapRefresh.textContent = "데이터 새로고침";
    }
  }
}

async function loadDashboardMarket(force = false) {
  if (!els.homeMarketList || (state.marketLoaded && !force)) return;
  els.homeMarketList.innerHTML = '<div class="home-news-empty">시장 데이터를 불러오는 중입니다.</div>';
  try {
    const res = await fetch(API.dashboardMarket);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      els.homeMarketList.innerHTML = '<div class="home-news-empty">표시할 시장 데이터가 없습니다.</div>';
      state.marketLoaded = true;
      return;
    }
    els.homeMarketList.innerHTML = items.map((item) => {
      const r = item.returns || {};
      const dayCls = Number(r["1d"]) >= 0 ? "up" : "down";
      const freshness = item.freshness_status || "unknown";
      const usable = isDecisionUsableMarketItem(item);
      const ageText = Number.isFinite(Number(item.age_minutes)) ? `${Math.round(Number(item.age_minutes))}분` : "";
      const source = item.source || "";
      return `
        <article class="home-market-card ${usable ? "" : "stale"} ${escapeHtml(freshness)}">
          <div class="home-market-head">
            <span class="home-market-symbol">${escapeHtml(item.symbol || "")}</span>
            <span class="home-market-class">${escapeHtml(item.asset_class || "")}</span>
          </div>
          <div class="home-market-label">${escapeHtml(item.label || "")}</div>
          <div class="home-market-price">${item.price === null || item.price === undefined ? "-" : escapeHtml(String(item.price))}</div>
          <div class="home-market-returns">
            <span class="${dayCls}">1D ${escapeHtml(fmtPct(r["1d"]))}</span>
            <span>1M ${escapeHtml(fmtPct(r["1m"]))}</span>
          </div>
          <div class="home-market-meta">
            <span>${escapeHtml(item.as_of || "기준일 미확인")}</span>
            <span>${escapeHtml(source)}</span>
          </div>
          <div class="home-market-freshness ${usable ? "ok" : "warn"}">
            <span>${escapeHtml(FRESHNESS_LABELS[freshness] || freshness)}</span>
            ${ageText ? `<span>${escapeHtml(ageText)}</span>` : ""}
            ${usable ? "" : "<strong>의사결정 제외</strong>"}
          </div>
        </article>
      `;
    }).join("");
    state.marketLoaded = true;
  } catch (err) {
    els.homeMarketList.innerHTML = `<div class="home-news-empty">시장 데이터 로드 실패: ${escapeHtml(err.message || err)}</div>`;
  }
}

function decisionStatusClass(status) {
  const key = String(status || "").toLowerCase();
  if (["ok", "success"].includes(key)) return "ok";
  if (["failed", "fail", "error"].includes(key)) return "fail";
  if (["partial", "warn", "stale", "empty", "credentials_missing", "dependency_missing"].includes(key)) return "warn";
  return "muted";
}

function decisionStatusLabel(status) {
  const key = String(status || "").toLowerCase();
  if (key === "success" || key === "ok") return "정상";
  if (key === "failed" || key === "fail" || key === "error") return "실패";
  if (key === "partial") return "부분";
  if (key === "warn" || key === "stale") return "경고";
  if (key === "empty") return "비어 있음";
  return status || "미확인";
}

function decisionEmpty(message) {
  return `<div class="home-news-empty">${escapeHtml(message)}</div>`;
}

function decisionMetric(label, value, status = "") {
  return `
    <div class="decision-metric ${escapeHtml(decisionStatusClass(status))}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value ?? "-")}</strong>
    </div>
  `;
}

function numberInputValue(el, fallback, { min = -Infinity, max = Infinity } = {}) {
  const n = Number(el?.value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function textInputValue(el) {
  return String(el?.value || "").trim() || null;
}

function priceValue(row) {
  const value = row?.adjusted_close ?? row?.close;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function pctReturnFromRows(rows, periods) {
  if (!Array.isArray(rows) || rows.length < periods + 1) return null;
  const last = priceValue(rows[rows.length - 1]);
  const prior = priceValue(rows[rows.length - 1 - periods]);
  return last !== null && prior ? (last / prior - 1) * 100 : null;
}

function dailyReturnsFromRows(rows) {
  const returns = [];
  for (let i = 1; i < rows.length; i += 1) {
    const prev = priceValue(rows[i - 1]);
    const current = priceValue(rows[i]);
    if (prev && current !== null) returns.push(current / prev - 1);
  }
  return returns;
}

function stdev(values) {
  const clean = values.map(Number).filter(Number.isFinite);
  if (clean.length < 2) return 0;
  const mean = clean.reduce((sum, value) => sum + value, 0) / clean.length;
  return Math.sqrt(clean.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (clean.length - 1));
}

function annualizedVol(rows, periods = 21) {
  const returns = dailyReturnsFromRows(rows).slice(-periods);
  if (returns.length < 2) return null;
  return stdev(returns) * Math.sqrt(252) * 100;
}

function maxDrawdownPct(rows) {
  let peak = -Infinity;
  let maxDrawdown = 0;
  rows.forEach((row) => {
    const price = priceValue(row);
    if (price === null) return;
    peak = Math.max(peak, price);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, price / peak - 1);
  });
  return maxDrawdown * 100;
}

function fmtMetricRatio(value) {
  const n = Number(value);
  return Number.isFinite(n) ? fmtPct(n * 100) : "-";
}

function fmtDecimal(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "-";
}

function metricStatusForPct(value, inverse = false) {
  if (value === null || value === undefined || value === "") return "warn";
  const n = Number(value);
  if (!Number.isFinite(n)) return "warn";
  if (inverse) return n <= 0 ? "ok" : "warn";
  return n >= 0 ? "ok" : "warn";
}

function renderMiniPriceLineChart(rows) {
  const points = rows
    .slice(-80)
    .map((row) => ({ date: row.date || "", value: priceValue(row) }))
    .filter((row) => row.value !== null);
  if (points.length < 2) return "";
  const width = 640;
  const height = 132;
  const padX = 14;
  const padY = 16;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const xStep = (width - padX * 2) / Math.max(1, points.length - 1);
  const xy = points.map((point, index) => {
    const x = padX + index * xStep;
    const y = height - padY - ((point.value - min) / range) * (height - padY * 2);
    return { ...point, x, y };
  });
  const linePoints = xy.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const areaPoints = `${padX},${height - padY} ${linePoints} ${width - padX},${height - padY}`;
  const first = points[0];
  const last = points[points.length - 1];
  const changePct = first.value ? (last.value / first.value - 1) * 100 : null;
  const changeClass = Number(changePct) >= 0 ? "ok" : "warn";
  return `
    <div class="mini-price-line" aria-label="최근 종가 선 차트">
      <div class="mini-price-line-head">
        <span>${escapeHtml(first.date || "-")} -> ${escapeHtml(last.date || "-")}</span>
        <strong class="${escapeHtml(changeClass)}">${escapeHtml(changePct === null ? "-" : fmtPct(changePct))}</strong>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="최근 ${escapeHtml(String(points.length))}개 가격 추이">
        <polygon points="${areaPoints}" class="mini-price-area"></polygon>
        <polyline points="${linePoints}" class="mini-price-stroke"></polyline>
        <circle cx="${xy[xy.length - 1].x.toFixed(1)}" cy="${xy[xy.length - 1].y.toFixed(1)}" r="4" class="mini-price-last"></circle>
      </svg>
      <div class="mini-price-line-foot">
        <span>저점 ${escapeHtml(fmtDecimal(min, 2))}</span>
        <span>고점 ${escapeHtml(fmtDecimal(max, 2))}</span>
        <span>최근 ${escapeHtml(fmtDecimal(last.value, 2))}</span>
      </div>
    </div>
  `;
}

function renderRecentPriceRows(rows) {
  return `
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>일자</th><th>종가</th><th>거래량</th><th>소스</th></tr></thead>
        <tbody>
          ${rows.slice(-6).reverse().map((row) => `
            <tr>
              <td>${escapeHtml(row.date || "-")}</td>
              <td>${escapeHtml(fmtDecimal(priceValue(row), 2))}</td>
              <td>${escapeHtml(_fmtNumber(row.volume))}</td>
              <td>${escapeHtml(row.source || "-")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderMetricGrid(metrics, status = "ok") {
  const rows = [
    ["총수익", fmtMetricRatio(metrics.total_return)],
    ["CAGR", fmtMetricRatio(metrics.cagr)],
    ["변동성", fmtMetricRatio(metrics.volatility)],
    ["Sharpe", fmtDecimal(metrics.sharpe, 2)],
    ["Sortino", fmtDecimal(metrics.sortino, 2)],
    ["MDD", fmtMetricRatio(metrics.max_drawdown)],
    ["Calmar", fmtDecimal(metrics.calmar, 2)],
    ["회전율", fmtDecimal(metrics.turnover, 2)],
    ["노출도", fmtMetricRatio(metrics.exposure)],
    ["거래 수", _fmtNumber(metrics.trade_count)],
  ];
  return `<div class="decision-metric-grid dense">${rows.map(([label, value]) => decisionMetric(label, value, status)).join("")}</div>`;
}

function backtestMetricsWithDerivedTotals(metrics, equityCurve) {
  const out = { ...(metrics || {}) };
  if (out.total_return === undefined || out.total_return === null) {
    const points = Array.isArray(equityCurve) ? equityCurve : [];
    const first = Number(points[0]?.equity);
    const last = Number(points[points.length - 1]?.equity);
    if (Number.isFinite(first) && first !== 0 && Number.isFinite(last)) {
      out.total_return = last / first - 1;
    }
  }
  return out;
}

function backtestRequestFromControls() {
  const tickers = parseTickerInput(els.backtestTicker?.value || "");
  const benchmark = normalizeTickerToken(els.backtestBenchmark?.value || "SPY") || "SPY";
  return {
    tickers,
    strategy: els.backtestStrategy?.value || "buy_and_hold",
    benchmark,
    compare_benchmark: !!els.backtestBenchmarkCompare?.checked,
    start_date: textInputValue(els.backtestStartDate),
    end_date: textInputValue(els.backtestEndDate),
    lookback_days: numberInputValue(els.backtestLookbackDays, 756, { min: 2, max: 5000 }),
    short_window: numberInputValue(els.backtestShortWindow, 20, { min: 1, max: 252 }),
    long_window: numberInputValue(els.backtestLongWindow, 50, { min: 2, max: 756 }),
    top_n: numberInputValue(els.backtestTopN, 1, { min: 1, max: 50 }),
    rebalance_every: numberInputValue(els.backtestRebalanceEvery, 21, { min: 1, max: 252 }),
    require_fresh_prices: !!els.backtestRequireFresh?.checked,
    use_research_score: !!els.backtestUseResearchScore?.checked,
    transaction_cost_bps: numberInputValue(els.backtestCostBps, 5, { min: 0, max: 1000 }),
    slippage_bps: numberInputValue(els.backtestSlippageBps, 2, { min: 0, max: 1000 }),
  };
}

function syncPortfolioFromBacktest() {
  const request = state.lastBacktestRequest || backtestRequestFromControls();
  if (els.portfolioTickers) els.portfolioTickers.value = (request.tickers || []).join(",");
  if (els.portfolioStartDate) els.portfolioStartDate.value = request.start_date || "";
  if (els.portfolioEndDate) els.portfolioEndDate.value = request.end_date || "";
  if (els.portfolioLookbackDays) els.portfolioLookbackDays.value = String(request.lookback_days || 756);
  if (els.portfolioBenchmark) els.portfolioBenchmark.value = request.benchmark || (request.tickers || [])[0] || "SPY";
  if (els.backtestBenchmark) els.backtestBenchmark.value = request.benchmark || "SPY";
}

async function loadDataHealth(force = false) {
  if (!els.homeDataHealth || (state.dataHealthLoaded && !force)) return;
  els.homeDataHealth.innerHTML = decisionEmpty("가격·거시·뉴스·공시 업데이트 상태를 확인하는 중입니다.");
  try {
    const res = await fetch(API.dataHealth);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const summary = data.summary || {};
    const status = summary.decision_status || data.status || "unknown";
    const counts = data.table_counts || {};
    const latest = data.latest_run || {};
    const providerRows = Array.isArray(data.recent_provider_status) ? data.recent_provider_status.slice(0, 6) : [];
    const qualityRows = Array.isArray(data.recent_quality_checks) ? data.recent_quality_checks.slice(0, 6) : [];
    const failedCount = Number(summary.failed_provider_rows || 0);
    const staleCount = Number(summary.stale_or_failed_quality_rows || 0);
    const coveredEmptyCount = Number(summary.covered_empty_provider_rows || 0);
    const runRows = Number(latest.rows_inserted || 0) + Number(latest.rows_updated || 0);
    els.homeDataHealth.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
        <span>${escapeHtml(latest.finished_at || latest.started_at || "업데이트 실행 이력 없음")} · ${escapeHtml(latest.market || "all")}</span>
      </div>
      <div class="decision-summary ${escapeHtml(decisionStatusClass(status))}">
        ${failedCount || staleCount
          ? `주의 필요: provider 실패 ${failedCount}건, 품질 경고 ${staleCount}건`
          : `업데이트 ${escapeHtml(latest.status || "ok")} · 이번 실행 반영 ${escapeHtml(_fmtNumber(runRows))}행${coveredEmptyCount ? ` · 적용 불가 empty ${escapeHtml(_fmtNumber(coveredEmptyCount))}건 정상 처리` : ""}`}
      </div>
      <div class="decision-metric-grid">
        ${decisionMetric("가격 행", _fmtNumber(counts.prices_daily), status)}
        ${decisionMetric("거시 관측치", _fmtNumber(counts.macro_observations), status)}
        ${decisionMetric("뉴스 evidence", _fmtNumber(counts.news_articles), counts.news_articles ? "ok" : "warn")}
        ${decisionMetric("공시 evidence", _fmtNumber(counts.filings), counts.filings ? "ok" : "warn")}
      </div>
      <div class="decision-section-title">최근 공급자 상태</div>
      <div class="decision-list">
        ${providerRows.length ? providerRows.map((row) => `
          <div class="decision-list-row">
            <span>${escapeHtml(row.provider || "provider")}${row.ticker ? ` · ${escapeHtml(row.ticker)}` : ""}${row.raw_status === "empty" ? " · empty 보강" : ""}</span>
            <strong class="${escapeHtml(decisionStatusClass(row.status))}">${escapeHtml(decisionStatusLabel(row.status || "unknown"))}</strong>
          </div>
        `).join("") : '<div class="muted small">No provider status rows yet.</div>'}
      </div>
      <div class="decision-section-title">최근 품질 점검</div>
      <div class="decision-list compact">
        ${qualityRows.length ? qualityRows.map((row) => `
          <div class="decision-list-row">
            <span>${escapeHtml(row.check_name || "quality")}${row.entity_id ? ` · ${escapeHtml(row.entity_id)}` : ""}</span>
            <strong class="${escapeHtml(decisionStatusClass(row.status))}">${escapeHtml(row.status || "unknown")}</strong>
          </div>
        `).join("") : '<div class="muted small">No quality checks recorded yet.</div>'}
      </div>
    `;
    state.dataHealthLoaded = true;
  } catch (err) {
    els.homeDataHealth.innerHTML = decisionEmpty(`Data health failed: ${err.message || err}`);
  }
}

async function loadAssetDetail() {
  if (!els.assetDetailSurface || !els.assetDetailTicker) return;
  const ticker = normalizeTickerToken(els.assetDetailTicker.value || "");
  if (!ticker) {
    els.assetDetailSurface.innerHTML = decisionEmpty("티커를 입력해야 합니다.");
    return;
  }
  els.assetDetailSurface.innerHTML = decisionEmpty(`${ticker} 저장 가격과 리스크 지표를 계산하는 중입니다.`);
  try {
    const res = await fetch(API.dataPrices(ticker, 756));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const latest = data.latest || {};
    if (!data.count) {
      els.assetDetailSurface.innerHTML = decisionEmpty(`${ticker} 저장 가격이 없습니다. daily_update를 먼저 실행해야 합니다.`);
      return;
    }
    const rows = Array.isArray(data.items) ? data.items : [];
    const lastPrice = priceValue(rows[rows.length - 1] || latest);
    const returns = {
      "1D": pctReturnFromRows(rows, 1),
      "1W": pctReturnFromRows(rows, 5),
      "1M": pctReturnFromRows(rows, 21),
      "3M": pctReturnFromRows(rows, 63),
      "6M": pctReturnFromRows(rows, 126),
      "1Y": pctReturnFromRows(rows, 252),
    };
    const vol20 = annualizedVol(rows, 21);
    const vol60 = annualizedVol(rows, 63);
    const mdd = maxDrawdownPct(rows);
    const values = rows.map(priceValue).filter((value) => value !== null);
    const high = values.length ? Math.max(...values.slice(-252)) : null;
    const low = values.length ? Math.min(...values.slice(-252)) : null;
    const latestDate = latest.date || rows[rows.length - 1]?.date || "-";
    els.assetDetailSurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ok">정상</span>
        <span>${escapeHtml(String(data.count))}행 · ${escapeHtml(latest.source || "소스 미확인")} · 수집 ${escapeHtml(latest.collected_at || "-")}</span>
      </div>
      <div class="decision-metric-grid dense">
        ${decisionMetric("기준일", latestDate, "ok")}
        ${decisionMetric("종가", fmtDecimal(lastPrice, 2), "ok")}
        ${decisionMetric("거래량", _fmtNumber(latest.volume), "ok")}
        ${decisionMetric("52W 범위", `${fmtDecimal(low, 2)} / ${fmtDecimal(high, 2)}`, high ? "ok" : "warn")}
        ${Object.entries(returns).map(([label, value]) => decisionMetric(label, value === null ? "-" : fmtPct(value), metricStatusForPct(value))).join("")}
        ${decisionMetric("20D Vol", vol20 === null ? "-" : fmtPct(vol20), vol20 === null ? "warn" : "ok")}
        ${decisionMetric("60D Vol", vol60 === null ? "-" : fmtPct(vol60), vol60 === null ? "warn" : "ok")}
        ${decisionMetric("MDD", fmtPct(mdd), metricStatusForPct(mdd, true))}
      </div>
      ${renderMiniPriceLineChart(rows)}
      ${renderRecentPriceRows(rows)}
    `;
  } catch (err) {
    els.assetDetailSurface.innerHTML = decisionEmpty(`자산 상세 조회 실패: ${err.message || err}`);
  }
}

function quantFeatureRequestFromControls() {
  const request = backtestRequestFromControls();
  const payload = {
    tickers: request.tickers,
    benchmark: request.benchmark || "SPY",
    start_date: request.start_date,
    end_date: request.end_date,
    freshness_profile: els.backtestFreshnessProfile?.value || "research_default",
    features: [
      { id: "momentum_63d" },
      { id: "realized_vol_21d" },
      { id: "drawdown_current" },
      { id: "ma_ratio_20_50" },
      { id: "relative_strength_spy_63d" },
    ],
  };
  if (els.backtestRequireFresh?.checked) payload.require_fresh_prices = true;
  return payload;
}

function quantSignalTemplateFromStrategy(strategy) {
  const clean = String(strategy || "").toLowerCase();
  if (clean === "momentum_ranking") return "momentum_ranking";
  if (clean === "research_confirmed_momentum") return "research_confirmed_momentum";
  if (clean === "moving_average") return "moving_average_trend";
  if (clean === "volatility_targeting") return "volatility_targeting";
  if (clean === "buy_and_hold") return "buy_and_hold";
  return "momentum_ranking";
}

const QUANT_TEMPLATE_LABELS = {
  buy_and_hold: "매수 후 보유",
  moving_average_trend: "이동평균 추세",
  volatility_targeting: "변동성 타깃",
  momentum_ranking: "모멘텀 랭킹",
  research_confirmed_momentum: "리서치 확인 모멘텀",
};

const PORTFOLIO_METHOD_LABELS = {
  equal_weight: "동일 비중",
  inverse_volatility: "역변동성",
  risk_parity: "리스크 패리티",
  minimum_volatility: "최소 변동성",
  max_sharpe: "최대 샤프",
  momentum_tilt: "모멘텀 틸트",
};

function quantTemplateLabel(template) {
  return QUANT_TEMPLATE_LABELS[String(template || "")] || String(template || "전략");
}

function portfolioMethodLabel(method) {
  return PORTFOLIO_METHOD_LABELS[String(method || "")] || String(method || "배분 방식");
}

function quantBacktestRequestFromControls() {
  const request = backtestRequestFromControls();
  const payload = {
    strategy_id: state.activeStrategyId || els.backtestStrategyRegistry?.value || null,
    tickers: request.tickers,
    benchmark: request.benchmark || "SPY",
    template: quantSignalTemplateFromStrategy(request.strategy),
    start_date: request.start_date,
    end_date: request.end_date,
    freshness_profile: els.backtestFreshnessProfile?.value || "research_default",
    rebalance_every: request.rebalance_every,
    lookback: request.short_window,
    top_n: request.top_n,
    portfolio_method: els.portfolioMethod?.value || "equal_weight",
    transaction_cost_bps: request.transaction_cost_bps,
    slippage_bps: request.slippage_bps,
    use_research_score: request.use_research_score,
  };
  if (els.backtestRequireFresh?.checked) payload.require_fresh_prices = true;
  return payload;
}

function formatQuantValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  if (Math.abs(num) <= 1.5) return fmtMetricRatio(num);
  return fmtDecimal(num, 2);
}

function renderDiagnosticsChips(values) {
  const items = Array.isArray(values) ? values : [];
  if (!items.length) return '<span>진단 없음</span>';
  return items.slice(0, 6).map((item) => `<span>${escapeHtml(String(item))}</span>`).join("");
}

function renderResearchProvenancePanel(provenance) {
  const entries = Object.entries(provenance || {});
  if (!entries.length) return "";
  return `
    <div class="decision-section-title">리서치 확인</div>
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>종목</th><th>상태</th><th>점수</th><th>실행</th><th>근거</th><th>만료</th></tr></thead>
        <tbody>
          ${entries.map(([ticker, item]) => `
            <tr>
              <td>${escapeHtml(ticker)}</td>
              <td><span class="table-status ${escapeHtml(decisionStatusClass(item.status))}">${escapeHtml(item.status || "unknown")}</span></td>
              <td>${escapeHtml(formatQuantValue(item.score))}</td>
              <td>${escapeHtml(item.run_id || "-")}</td>
              <td>${escapeHtml(_fmtNumber((item.evidence_ids || []).length))}</td>
              <td>${escapeHtml(item.expires_at || "-")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderFreshnessAuditPanel(diagnostics) {
  const policy = diagnostics?.freshness_policy || {};
  const audits = Object.entries(diagnostics?.asset_freshness || {});
  if (!Object.keys(policy).length && !audits.length) return "";
  return `
    <div class="decision-section-title">데이터 신선도 정책</div>
    <div class="decision-chip-row">
      <span>${escapeHtml(policy.policy_id || "daily_price_policy")}</span>
      <span>기준일 ${escapeHtml(diagnostics.expected_latest_date || policy.expected_latest_date || "알 수 없음")}</span>
      <span>허용 지연 ${escapeHtml(String(policy.max_market_calendar_lag_days ?? "-"))}일</span>
      <span>강제 최신 ${policy.require_fresh_prices ? "켜짐" : "꺼짐"}</span>
    </div>
    ${audits.length ? `
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>종목</th><th>상태</th><th>최근일</th><th>지연</th><th>사유</th></tr></thead>
          <tbody>
            ${audits.map(([ticker, audit]) => `
              <tr>
                <td>${escapeHtml(ticker)}</td>
                <td><span class="table-status ${escapeHtml(decisionStatusClass(audit.freshness_status))}">${escapeHtml(audit.freshness_status || "unknown")}</span></td>
                <td>${escapeHtml(audit.latest_price_date || "unknown")}</td>
                <td>${escapeHtml(String(audit.market_calendar_lag_days ?? "-"))}</td>
                <td>${escapeHtml(audit.missing_reason || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    ` : ""}
  `;
}

function renderRebalanceSnapshots(weights) {
  const snapshots = (Array.isArray(weights) ? weights : [])
    .filter((row) => row && (row.selected || row.target_weights || row.weights))
    .slice(-5);
  if (!snapshots.length) return "";
  return `
    <div class="decision-section-title">리밸런싱 귀속</div>
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>신호일</th><th>체결일</th><th>선정</th><th>제외</th><th>회전율</th></tr></thead>
        <tbody>
          ${snapshots.map((row) => {
            const selected = Array.isArray(row.selected)
              ? row.selected.join(",")
              : Object.entries(row.weights || row.target_weights || {}).filter(([, weight]) => Number(weight) > 0).map(([ticker]) => ticker).join(",");
            const rejected = Array.isArray(row.rejected) ? row.rejected.join(",") : "";
            return `
              <tr>
                <td>${escapeHtml(row.signal_date || row.date || "")}</td>
                <td>${escapeHtml(row.execution_date || row.date || "")}</td>
                <td>${escapeHtml(selected || "-")}</td>
                <td>${escapeHtml(rejected || "-")}</td>
                <td>${escapeHtml(formatQuantValue(row.turnover ?? ""))}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderRiskContributionBars(contributions) {
  const entries = Object.entries(contributions || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (!entries.length) return "";
  return `
    <div class="portfolio-weight-list">
      ${entries.map(([ticker, contribution]) => `
        <div class="portfolio-weight-row">
          <span>${escapeHtml(ticker)}</span>
          <div><i style="width:${Math.max(2, Math.min(100, Number(contribution) * 100))}%"></i></div>
          <strong>${escapeHtml(fmtPct(Number(contribution) * 100))}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function renderCorrelationPreview(matrix) {
  const assets = Object.keys(matrix || {}).slice(0, 5);
  if (!assets.length) return "";
  return `
    <div class="decision-section-title">상관관계 행렬</div>
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th></th>${assets.map((asset) => `<th>${escapeHtml(asset)}</th>`).join("")}</tr></thead>
        <tbody>
          ${assets.map((rowAsset) => `
            <tr>
              <td>${escapeHtml(rowAsset)}</td>
              ${assets.map((colAsset) => `<td>${escapeHtml(fmtDecimal(matrix[rowAsset]?.[colAsset], 2))}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPortfolioDecisionBrief({ entries, portfolioMetrics, diagnostics, riskContributions, method, benchmark, maxWeight }) {
  const largest = entries[0] || ["-", 0];
  const largestWeight = Number(largest[1] || 0);
  const effectivePositions = Number(diagnostics.effective_number_of_positions);
  const beta = Number(portfolioMetrics.beta_to_benchmark);
  const trackingError = Number(portfolioMetrics.tracking_error);
  const infoRatio = Number(portfolioMetrics.information_ratio);
  const maxRiskEntry = Object.entries(riskContributions || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))[0] || ["-", 0];
  const concentrationStatus = largestWeight > Math.min(0.5, Number(maxWeight || 1) * 0.95) ? "warn" : "ok";
  const betaStatus = Number.isFinite(beta) && beta > 1.1 ? "warn" : "ok";
  const teStatus = Number.isFinite(trackingError) && trackingError > 0.12 ? "warn" : "ok";
  const rebalanceText = entries
    .slice(0, 4)
    .map(([ticker, weight]) => `${ticker} ${fmtPct(Number(weight) * 100)}`)
    .join(" · ");
  return `
    <div class="decision-practical-grid portfolio-practical-grid">
      ${decisionMetric("배분 방식", portfolioMethodLabel(method), "ok")}
      ${decisionMetric("최대 편입", `${largest[0]} ${fmtPct(largestWeight * 100)}`, concentrationStatus)}
      ${decisionMetric("효과 포지션", fmtDecimal(effectivePositions, 2), Number.isFinite(effectivePositions) && effectivePositions >= 2 ? "ok" : "warn")}
      ${decisionMetric("최대 위험 기여", `${maxRiskEntry[0]} ${fmtPct(Number(maxRiskEntry[1]) * 100)}`, Number(maxRiskEntry[1]) > 0.5 ? "warn" : "ok")}
      ${decisionMetric(`${benchmark} 베타`, fmtDecimal(beta, 2), betaStatus)}
      ${decisionMetric("추적오차", fmtMetricRatio(trackingError), teStatus)}
      ${decisionMetric("정보비율", fmtDecimal(infoRatio, 2), Number.isFinite(infoRatio) && infoRatio > 0 ? "ok" : "warn")}
      ${decisionMetric("리밸런싱 초안", rebalanceText || "-", entries.length ? "ok" : "warn")}
    </div>
    <div class="decision-action-list">
      <div><strong>운용 체크</strong><span>${largestWeight > 0.5 ? "단일 종목 집중도가 높습니다. 최대 비중을 낮추거나 역변동성/리스크 패리티를 비교하세요." : "집중도는 제한 안에 있습니다. 위험 기여도와 상관관계가 같은 방향으로 몰리는지만 확인하세요."}</span></div>
      <div><strong>벤치마크 체크</strong><span>${Number.isFinite(beta) ? `${benchmark} 대비 베타 ${fmtDecimal(beta, 2)}, 추적오차 ${fmtMetricRatio(trackingError)}입니다. 목표가 절대수익이면 낮은 추적오차보다 MDD와 변동성을 우선 보세요.` : "벤치마크 대비 민감도를 계산할 수 없습니다. 벤치마크 가격 누락 여부를 확인하세요."}</span></div>
      <div><strong>실행 체크</strong><span>목표 비중은 주문 전 현재 보유 비중, 세금, 최소 주문 단위, 거래비용을 반영해 최종 주문량으로 변환해야 합니다.</span></div>
    </div>
  `;
}

function compactArtifactPath(path) {
  const raw = String(path || "");
  if (!raw) return "-";
  const parts = raw.replace(/\\/g, "/").split("/");
  return parts.slice(-4).join("/");
}

function renderQuantExportControls(runId) {
  if (!runId) return "";
  const safeRunId = escapeHtml(runId);
  return `
    <div class="decision-chip-row">
      <button type="button" class="linkish decision-inline-action" data-action="export-backtest" data-format="jsonl" data-run-id="${safeRunId}">export JSONL</button>
      <button type="button" class="linkish decision-inline-action" data-action="export-backtest" data-format="csv" data-run-id="${safeRunId}">export CSV</button>
      <button type="button" class="linkish decision-inline-action" data-action="export-backtest" data-format="parquet" data-run-id="${safeRunId}">export Parquet</button>
      <label class="decision-inline-select">
        <span>retention</span>
        <select data-action="export-retention" aria-label="Quant export retention">
          <option value="0">No cleanup</option>
          <option value="3">Keep last 3</option>
          <option value="5">Keep last 5</option>
          <option value="10">Keep last 10</option>
        </select>
      </label>
      <button type="button" class="linkish decision-inline-action" data-action="export-history" data-run-id="${safeRunId}">export history</button>
      <button type="button" class="linkish decision-inline-action" data-action="export-cleanup-preview" data-run-id="${safeRunId}">cleanup preview</button>
      <button type="button" class="linkish decision-inline-action" data-action="verify-export" data-run-id="${safeRunId}">verify latest export</button>
    </div>
  `;
}

function renderDecisionLineChart(rows, key, label, status = "ok") {
  const values = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ date: row.date || "", value: Number(row[key]) }))
    .filter((row) => Number.isFinite(row.value));
  if (values.length < 2) return "";
  const width = 320;
  const height = 88;
  const pad = 8;
  const nums = values.map((row) => row.value);
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const points = values.map((row, idx) => {
    const x = pad + (idx / Math.max(1, values.length - 1)) * (width - pad * 2);
    const y = height - pad - ((row.value - min) / span) * (height - pad * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const latest = values[values.length - 1];
  const latestValue = key === "equity" ? fmtDecimal(latest.value, 3) : formatQuantValue(latest.value);
  return `
    <div class="decision-chart">
      <div class="decision-chart-head">
        <span>${escapeHtml(label)}</span>
        <strong class="${escapeHtml(decisionStatusClass(status))}">${escapeHtml(latestValue)}</strong>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)} curve">
        <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"></polyline>
      </svg>
      <div class="decision-chart-foot">
        <span>${escapeHtml(values[0].date)}</span>
        <span>${escapeHtml(latest.date)}</span>
      </div>
    </div>
  `;
}

function normalizedCurve(rows, key = "equity") {
  const values = (Array.isArray(rows) ? rows : [])
    .map((row) => ({ date: row.date || "", value: Number(row[key]) }))
    .filter((row) => row.date && Number.isFinite(row.value) && row.value > 0);
  if (values.length < 2) return [];
  const base = values[0].value || 1;
  return values.map((row) => ({ date: row.date, value: row.value / base }));
}

function renderBenchmarkComparisonChart(data, status = "ok") {
  const strategy = normalizedCurve(data.equity_curve, "equity");
  const benchmark = normalizedCurve(data.benchmark_curve, "equity");
  if (strategy.length < 2 || benchmark.length < 2) return "";
  const width = 640;
  const height = 112;
  const pad = 10;
  const allValues = [...strategy, ...benchmark].map((row) => row.value);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max - min || 1;
  const toPoints = (rows) => rows.map((row, idx) => {
    const x = pad + (idx / Math.max(1, rows.length - 1)) * (width - pad * 2);
    const y = height - pad - ((row.value - min) / span) * (height - pad * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const strategyLatest = strategy[strategy.length - 1]?.value ?? 1;
  const benchmarkLatest = benchmark[benchmark.length - 1]?.value ?? 1;
  const benchmarkTicker = data.benchmark_ticker || data.benchmark || "SPY";
  return `
    <div class="decision-chart decision-chart-wide">
      <div class="decision-chart-head">
        <span>수익 곡선 비교</span>
        <strong class="${escapeHtml(decisionStatusClass(status))}">전략 ${escapeHtml(fmtPct((strategyLatest - 1) * 100))} · ${escapeHtml(benchmarkTicker)} ${escapeHtml(fmtPct((benchmarkLatest - 1) * 100))}</strong>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="백테스트 벤치마크 비교">
        <polyline points="${toPoints(benchmark)}" fill="none" stroke="#60a5fa" stroke-width="2" vector-effect="non-scaling-stroke"></polyline>
        <polyline points="${toPoints(strategy)}" fill="none" stroke="#34d399" stroke-width="2.4" vector-effect="non-scaling-stroke"></polyline>
      </svg>
      <div class="decision-chart-foot">
        <span><i class="legend-line strategy"></i>전략</span>
        <span><i class="legend-line benchmark"></i>${escapeHtml(benchmarkTicker)} 벤치마크</span>
      </div>
    </div>
  `;
}

async function attachBenchmarkComparison(data, request = {}) {
  if (!data || !request?.compare_benchmark) return data;
  const benchmarkTicker = normalizeTickerToken(request.benchmark || data.benchmark || "SPY") || "SPY";
  try {
    const res = await fetch(API.dataPrices(benchmarkTicker, 5000));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    const rows = Array.isArray(payload.items) ? payload.items : [];
    const start = data.date_range?.start || request.start_date || "";
    const end = data.date_range?.end || request.end_date || "";
    const filtered = rows.filter((row) => {
      const date = row.date || "";
      if (start && date < start) return false;
      if (end && date > end) return false;
      return priceValue(row) !== null;
    });
    const base = priceValue(filtered[0]);
    if (!base) throw new Error(`${benchmarkTicker} price history is unavailable`);
    return {
      ...data,
      benchmark_ticker: benchmarkTicker,
      benchmark_curve: filtered.map((row) => ({
        date: row.date || "",
        equity: Number((priceValue(row) / base).toFixed(8)),
      })),
    };
  } catch (err) {
    return {
      ...data,
      benchmark_ticker: benchmarkTicker,
      benchmark_warning: `벤치마크 비교 불가: ${err.message || err}`,
    };
  }
}

function renderQuantDiagnosticsPanel(data) {
  const diagnostics = data.diagnostics || {};
  const artifacts = data.artifacts || {};
  const priceCounts = diagnostics.price_counts || {};
  const chips = [
    `룩어헤드 ${diagnostics.lookahead_safe ? "안전" : "점검 필요"}`,
    `시그널 지연 ${diagnostics.signal_shift_bars ?? 1}봉`,
    diagnostics.execution_assumption || "next_bar_close",
    diagnostics.data_source || "data_mart",
    ...Object.entries(priceCounts).map(([ticker, count]) => `${ticker} ${_fmtNumber(count)}행`),
  ];
  return `
    <div class="decision-section-title">진단</div>
    <div class="decision-chip-row">${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>
    ${(diagnostics.missing_assets || []).length ? `<div class="decision-warning">누락 종목: ${escapeHtml(diagnostics.missing_assets.join(", "))}</div>` : ""}
    ${(diagnostics.stale_assets || []).length ? `<div class="decision-warning">오래된 가격: ${escapeHtml(diagnostics.stale_assets.join(", "))}</div>` : ""}
    ${(diagnostics.warnings || []).length ? `<div class="decision-warning">${escapeHtml(diagnostics.warnings.join(" "))}</div>` : ""}
    ${renderFreshnessAuditPanel(diagnostics)}
    <div class="decision-section-title">산출물</div>
    <div class="decision-list compact">
      ${["manifest", "config", "metrics", "diagnostics", "equity_curve", "drawdown_curve", "trades", "signals", "weights", "replay_report"].map((name) => `
        <div class="decision-list-row">
          <span>${escapeHtml(name)}</span>
          <strong>${escapeHtml(compactArtifactPath(artifacts[name]))}</strong>
        </div>
      `).join("")}
    </div>
    ${renderQuantExportControls(data.run_id)}
  `;
}

function renderQuantBacktestTables(data) {
  const trades = Array.isArray(data.trades) ? data.trades.slice(-8) : [];
  const signals = Array.isArray(data.signals) ? data.signals.slice(0, 8) : [];
  const weights = Array.isArray(data.weights) ? data.weights : [];
  return `
    ${signals.length ? `
      <div class="decision-section-title">최근 시그널</div>
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>종목</th><th>일자</th><th>점수</th><th>신호</th><th>체결일</th></tr></thead>
          <tbody>
            ${signals.map((row) => `
              <tr>
                <td>${escapeHtml(row.ticker || "")}</td>
                <td>${escapeHtml(row.date || "")}</td>
                <td>${escapeHtml(fmtDecimal(row.final_score, 3))}</td>
                <td><span class="table-status ${Number(row.signal || 0) > 0 ? "ok" : "warn"}">${escapeHtml(fmtDecimal(row.signal, 2))}</span></td>
                <td>${escapeHtml(row.execution_date || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    ` : ""}
    ${trades.length ? `
      <div class="decision-section-title">최근 거래</div>
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>일자</th><th>종목</th><th>액션</th><th>비중</th><th>비용</th></tr></thead>
          <tbody>
            ${trades.map((row) => {
              const assetText = row.ticker || row.asset || (Array.isArray(row.selected) ? row.selected.join(",") : "") || "portfolio";
              const actionText = row.action || row.side || row.type || (row.turnover !== undefined ? "rebalance" : "");
              const weightValue = row.weight ?? row.target_weight ?? row.quantity ?? row.turnover;
              return `
                <tr>
                  <td>${escapeHtml(row.date || row.execution_date || "")}</td>
                  <td>${escapeHtml(assetText)}</td>
                  <td>${escapeHtml(actionText)}</td>
                  <td>${escapeHtml(formatQuantValue(weightValue))}</td>
                  <td>${escapeHtml(formatQuantValue(row.cost ?? row.transaction_cost ?? ""))}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    ` : ""}
    ${renderRebalanceSnapshots(weights)}
  `;
}

function renderQuantBacktestResult(data, request = {}) {
  if (!els.backtestSurface) return;
  const metrics = backtestMetricsWithDerivedTotals(data.metrics || {}, data.equity_curve);
  const status = data.status || "unknown";
  const benchmarkWarning = data.benchmark_warning
    ? `<div class="decision-warning">${escapeHtml(data.benchmark_warning)}</div>`
    : "";
  els.backtestSurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
      <span>${escapeHtml(data.run_id || "run pending")} · ${escapeHtml(data.date_range?.start || request.start_date || "-")} -> ${escapeHtml(data.date_range?.end || request.end_date || "-")}</span>
    </div>
    ${renderMetricGrid(metrics, status)}
    <div class="decision-chart-grid">
      ${renderDecisionLineChart(data.equity_curve, "equity", "수익 곡선", status)}
      ${renderDecisionLineChart(data.drawdown_curve, "drawdown", "MDD", Number(metrics.max_drawdown || 0) < -0.2 ? "warn" : status)}
      ${renderBenchmarkComparisonChart(data, status)}
    </div>
    ${benchmarkWarning}
    <div class="decision-assumption">
      전략 ${escapeHtml(request.strategy_id || data.config?.strategy_id || state.activeStrategyId || "임시")} · 템플릿 ${escapeHtml(quantTemplateLabel(data.template || request.template || "unknown"))} · 벤치마크 ${escapeHtml(data.benchmark_ticker || data.benchmark || request.benchmark || "-")} · 비용 ${escapeHtml(String(request.transaction_cost_bps ?? data.config?.transaction_cost_bps ?? "-"))}bps · 슬리피지 ${escapeHtml(String(request.slippage_bps ?? data.config?.slippage_bps ?? "-"))}bps
    </div>
    ${renderQuantBacktestTables(data)}
    ${renderQuantDiagnosticsPanel(data)}
    <button type="button" class="linkish decision-inline-action" data-action="sync-backtest-portfolio">이 조건을 포트폴리오에 적용</button>
    ${data.run_id ? `<button type="button" class="linkish decision-inline-action" data-action="replay-backtest" data-run-id="${escapeHtml(data.run_id)}">재현 비교</button>` : ""}
    ${data.run_id ? `<button type="button" class="linkish decision-inline-action" data-action="replay-reports" data-run-id="${escapeHtml(data.run_id)}">재현 이력</button>` : ""}
    ${status === "success" ? "" : decisionEmpty(data.reason || "저장 가격이 부족해 일부 결과만 표시됩니다.")}
  `;
}

function renderReplayReportHistoryTable(history) {
  const items = Array.isArray(history?.items) ? history.items : [];
  if (!items.length) return '<div class="decision-empty">No persisted replay reports yet.</div>';
  const metricKeys = ["total_return", "sharpe", "max_drawdown"].filter((key) =>
    items.some((item) => item.metric_deltas && item.metric_deltas[key] !== undefined)
  );
  return `
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead>
          <tr><th>Generated</th><th>Status</th><th>Config</th><th>Tolerance</th>${metricKeys.map((key) => `<th>${escapeHtml(key)}</th>`).join("")}<th>Report</th></tr>
        </thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td>${escapeHtml(fmtDate(item.generated_at) || "-")}</td>
              <td><span class="table-status ${escapeHtml(decisionStatusClass(item.status))}">${escapeHtml(item.status || "unknown")}</span></td>
              <td>${item.config_hash_match ? "match" : "changed"}</td>
              <td><span class="table-status ${item.tolerance_passed ? "ok" : "warn"}">${item.tolerance_passed ? "passed" : `fail ${escapeHtml(String(item.tolerance_failure_count || 0))}`}</span></td>
              ${metricKeys.map((key) => `<td>${escapeHtml(formatQuantValue(item.metric_deltas?.[key] ?? 0))}</td>`).join("")}
              <td>${escapeHtml(compactArtifactPath(item.report_path))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderArtifactExportSummary(data) {
  const files = data.files || {};
  const counts = data.row_counts || {};
  const dependency = data.dependency || {};
  const integrityFiles = data.integrity?.files || {};
  const retention = data.retention || {};
  const dependencyMessage = data.status === "dependency_missing"
    ? `<div class="decision-warning">${escapeHtml(dependency.message || "Optional export dependency is missing.")}</div>`
    : "";
  const retentionMessage = retention.retention_applied
    ? `<div class="decision-warning">Retention kept last ${escapeHtml(String(retention.keep_last_exports || 0))} export set(s); pruned ${escapeHtml(String(retention.pruned_export_count || 0))} older set(s).</div>`
    : "";
  return `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status || "success"))}">${escapeHtml(data.status || "success")}</span>
      <span>${escapeHtml(data.run_id || "")} ${escapeHtml(String(data.format || "").toUpperCase())} export</span>
    </div>
    <div class="decision-chip-row">
      <span>rows ${escapeHtml(_fmtNumber(counts.total || 0))}</span>
      <span>root ${escapeHtml(compactArtifactPath(data.export_root))}</span>
      <span>manifest ${escapeHtml(compactArtifactPath(files.manifest))}</span>
      ${dependency.engine ? `<span>engine ${escapeHtml(dependency.engine)}</span>` : ""}
    </div>
    ${dependencyMessage}
    ${retentionMessage}
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>Section</th><th>Rows</th><th>File</th><th>SHA-256</th><th>Bytes</th></tr></thead>
        <tbody>
          ${Object.keys(counts).filter((name) => name !== "total").map((name) => {
            const filePath = files[name] || files.jsonl || "";
            const integrity = integrityFiles[name] || (files[name] ? {} : integrityFiles.jsonl) || {};
            return `
              <tr>
                <td>${escapeHtml(name)}</td>
                <td>${escapeHtml(_fmtNumber(counts[name]))}</td>
                <td>${escapeHtml(compactArtifactPath(filePath))}</td>
                <td>${escapeHtml(String(integrity.sha256 || "").slice(0, 16) || "-")}</td>
                <td>${escapeHtml(_fmtNumber(integrity.size_bytes || 0))}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
    ${renderQuantExportControls(data.run_id)}
  `;
}

function renderArtifactExportHistory(data) {
  const items = Array.isArray(data.items) ? data.items : [];
  return `
    <div class="decision-status-row">
      <span class="decision-badge ok">${escapeHtml(data.status || "success")}</span>
      <span>${escapeHtml(data.run_id || "")} · ${escapeHtml(_fmtNumber(data.count || 0))} export manifest(s)</span>
    </div>
    ${renderQuantExportControls(data.run_id || "")}
    ${items.length ? `
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>Generated</th><th>Format</th><th>Status</th><th>Rows</th><th>Bytes</th><th>Integrity</th><th>Manifest</th><th>Verify</th></tr></thead>
          <tbody>
            ${items.map((item) => `
              <tr>
                <td>${escapeHtml(fmtDate(item.generated_at) || "-")}</td>
                <td>${escapeHtml(String(item.format || "unknown").toUpperCase())}</td>
                <td><span class="table-status ${escapeHtml(decisionStatusClass(item.status || "unknown"))}">${escapeHtml(item.status || "unknown")}</span></td>
                <td>${escapeHtml(_fmtNumber(item.total_rows || 0))}</td>
                <td>${escapeHtml(_fmtNumber(item.total_bytes || 0))}</td>
                <td>${item.integrity_available ? "sha256" : "missing"}</td>
                <td>${escapeHtml(compactArtifactPath(item.manifest_path))}</td>
                <td><button type="button" class="linkish" data-action="verify-export" data-run-id="${escapeHtml(data.run_id || "")}" data-manifest-path="${escapeHtml(item.manifest_path || "")}">verify</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    ` : decisionEmpty("No generated artifact exports have been saved for this run yet.")}
  `;
}

function renderArtifactExportCleanupPlan(data) {
  const kept = Array.isArray(data.kept_exports) ? data.kept_exports : [];
  const prune = Array.isArray(data.prune_exports) ? data.prune_exports : [];
  const applied = !!data.cleanup_applied;
  const statusText = applied ? "export cleanup applied" : "export cleanup preview";
  return `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status || "success"))}">${escapeHtml(data.status || "success")}</span>
      <span>${escapeHtml(data.run_id || "")} ${statusText}</span>
    </div>
    <div class="decision-chip-row">
      <span>policy ${escapeHtml(data.policy || "keep_last_exports")}</span>
      <span>keep last ${escapeHtml(_fmtNumber(data.keep_last_exports || 0))}</span>
      <span>exports ${escapeHtml(_fmtNumber(data.export_count || 0))}</span>
      <span>prune ${escapeHtml(_fmtNumber(data.prune_export_count || 0))}</span>
      <span>bytes ${escapeHtml(_fmtNumber(applied ? data.total_bytes_pruned || 0 : data.total_bytes_to_prune || 0))}</span>
    </div>
    ${renderQuantExportControls(data.run_id || "")}
    ${!applied && prune.length ? `
      <div class="decision-chip-row">
        <button type="button" class="linkish decision-inline-action" data-action="export-cleanup-apply" data-run-id="${escapeHtml(data.run_id || "")}" data-keep-last="${escapeHtml(String(data.keep_last_exports || 0))}">apply cleanup</button>
      </div>
    ` : ""}
    ${prune.length ? `
      <div class="decision-section-title">${applied ? "Pruned exports" : "Exports that would be pruned"}</div>
      ${renderArtifactExportCleanupTable(prune)}
    ` : decisionEmpty("No generated export directories are eligible for cleanup with this policy.")}
    ${kept.length ? `
      <div class="decision-section-title">Exports kept</div>
      ${renderArtifactExportCleanupTable(kept)}
    ` : ""}
  `;
}

function renderArtifactExportCleanupTable(items) {
  return `
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>Generated</th><th>Format</th><th>Status</th><th>Rows</th><th>Bytes</th><th>Directory</th></tr></thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td>${escapeHtml(fmtDate(item.generated_at) || "-")}</td>
              <td>${escapeHtml(String(item.format || "unknown").toUpperCase())}</td>
              <td><span class="table-status ${escapeHtml(decisionStatusClass(item.status || "unknown"))}">${escapeHtml(item.status || "unknown")}</span></td>
              <td>${escapeHtml(_fmtNumber(item.total_rows || 0))}</td>
              <td>${escapeHtml(_fmtNumber(item.total_bytes || item.directory_size_bytes || 0))}</td>
              <td>${escapeHtml(compactArtifactPath(item.directory || item.export_root || ""))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderArtifactExportVerification(data) {
  const files = data.files || {};
  const failures = Array.isArray(data.failures) ? data.failures : [];
  return `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status || "unknown"))}">${escapeHtml(data.status || "unknown")}</span>
      <span>${escapeHtml(data.run_id || "")} export integrity verification</span>
    </div>
    <div class="decision-chip-row">
      <span>checked ${escapeHtml(_fmtNumber(data.files_checked || 0))}</span>
      <span>passed ${escapeHtml(_fmtNumber(data.files_passed || 0))}</span>
      <span>failed ${escapeHtml(_fmtNumber(data.files_failed || 0))}</span>
      <span>format ${escapeHtml(String(data.format || "unknown").toUpperCase())}</span>
      <span>manifest ${escapeHtml(compactArtifactPath(data.manifest_path))}</span>
    </div>
    ${failures.length ? `<div class="decision-warning">${escapeHtml(failures.map((item) => `${item.file}:${item.reason}`).join(", "))}</div>` : ""}
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>File</th><th>Status</th><th>Expected SHA</th><th>Actual SHA</th><th>Expected bytes</th><th>Actual bytes</th></tr></thead>
        <tbody>
          ${Object.entries(files).map(([name, item]) => `
            <tr>
              <td>${escapeHtml(name)}</td>
              <td><span class="table-status ${item.status === "passed" ? "ok" : "fail"}">${escapeHtml(item.status || "unknown")}</span></td>
              <td>${escapeHtml(String(item.expected_sha256 || "").slice(0, 16) || "-")}</td>
              <td>${escapeHtml(String(item.actual_sha256 || "").slice(0, 16) || "-")}</td>
              <td>${escapeHtml(_fmtNumber(item.expected_size_bytes || 0))}</td>
              <td>${escapeHtml(_fmtNumber(item.actual_size_bytes || 0))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    ${renderQuantExportControls(data.run_id || "")}
  `;
}

function renderQuantReplayComparison(data) {
  if (!els.backtestSurface) return;
  const deltas = data.metric_deltas || {};
  const original = data.original_metrics || {};
  const replay = data.replay_metrics || {};
  const tolerancePolicy = data.tolerance_policy || {};
  const metricTolerances = tolerancePolicy.metrics || {};
  const toleranceFailures = Array.isArray(data.tolerance_failures) ? data.tolerance_failures : [];
  const keys = ["total_return", "cagr", "annualized_volatility", "sharpe", "sortino", "max_drawdown", "turnover", "exposure"]
    .filter((key) => original[key] !== undefined || replay[key] !== undefined || deltas[key] !== undefined);
  const status = data.status || "unknown";
  els.backtestSurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
      <span>${escapeHtml(data.run_id || "")} replayed as ${escapeHtml(data.replay_run_id || "")}</span>
    </div>
    <div class="decision-chip-row">
      <span>config hash ${data.config_hash_match ? "matched" : "changed"}</span>
      <span>original ${escapeHtml(String(data.original_config_hash || "-")).slice(0, 10)}</span>
      <span>replay ${escapeHtml(String(data.replay_config_hash || "-")).slice(0, 10)}</span>
      <span>lookahead ${data.diagnostics?.lookahead_safe ? "safe" : "check"}</span>
      <span>tolerance ${data.tolerance_passed ? "passed" : "check"}</span>
    </div>
    <div class="decision-chip-row">
      <button type="button" class="linkish decision-inline-action" data-action="replay-reports" data-run-id="${escapeHtml(data.run_id || "")}">replay report history</button>
    </div>
    ${renderQuantExportControls(data.run_id)}
    <div class="decision-section-title">Replay metric comparison</div>
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>Metric</th><th>Original</th><th>Replay</th><th>Delta</th><th>Tolerance</th></tr></thead>
        <tbody>
          ${keys.map((key) => `
            <tr>
              <td>${escapeHtml(key)}</td>
              <td>${escapeHtml(formatQuantValue(original[key]))}</td>
              <td>${escapeHtml(formatQuantValue(replay[key]))}</td>
              <td><span class="table-status ${Math.abs(Number(deltas[key] || 0)) <= Number(metricTolerances[key] ?? tolerancePolicy.default_abs ?? 0) ? "ok" : "warn"}">${escapeHtml(formatQuantValue(deltas[key] ?? 0))}</span></td>
              <td>${escapeHtml(formatQuantValue(metricTolerances[key] ?? tolerancePolicy.default_abs ?? 0))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    ${toleranceFailures.length ? `<div class="decision-warning">Replay tolerance failures: ${escapeHtml(toleranceFailures.map((item) => `${item.metric}=${item.abs_delta}`).join(", "))}</div>` : ""}
    <div class="decision-section-title">Lineage</div>
    <div class="decision-list compact">
      <div class="decision-list-row"><span>Original generated</span><strong>${escapeHtml(data.original_generated_at || "-")}</strong></div>
      <div class="decision-list-row"><span>Replay generated</span><strong>${escapeHtml(data.replay_generated_at || "-")}</strong></div>
      <div class="decision-list-row"><span>Original commit</span><strong>${escapeHtml(String(data.original_code_version?.git_commit || "-")).slice(0, 12)}</strong></div>
      <div class="decision-list-row"><span>Current commit</span><strong>${escapeHtml(String(data.current_code_version?.git_commit || "-")).slice(0, 12)}</strong></div>
      <div class="decision-list-row"><span>Replay report</span><strong>${escapeHtml(data.report_path || "-")}</strong></div>
    </div>
    <div class="decision-section-title">Replay report history</div>
    ${renderReplayReportHistoryTable(data.report_history || {})}
    ${(data.diagnostics?.warnings || []).length ? `<div class="decision-warning">${escapeHtml(data.diagnostics.warnings.join(" "))}</div>` : ""}
  `;
}

async function runQuantBacktestReplay(runId) {
  if (!runId || !els.backtestSurface) return;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} replay comparison is running.`);
  try {
    const res = await fetch(API.quantBacktestReplay(runId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persist_report: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    renderQuantReplayComparison(data);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Replay comparison failed: ${err.message || err}`);
  }
}

async function loadQuantReplayReports(runId) {
  if (!runId || !els.backtestSurface) return;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} replay report history is loading.`);
  try {
    const res = await fetch(`${API.quantBacktestReplayReports(runId)}?limit=20`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ok">${escapeHtml(data.status || "success")}</span>
        <span>${escapeHtml(data.run_id || runId)} · ${escapeHtml(_fmtNumber(data.count || 0))} replay reports</span>
      </div>
      <div class="decision-chip-row">
        <button type="button" class="linkish decision-inline-action" data-action="replay-backtest" data-run-id="${escapeHtml(runId)}">run new replay</button>
      </div>
      ${renderQuantExportControls(runId)}
      ${renderReplayReportHistoryTable(data)}
    `;
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Replay report history failed: ${err.message || err}`);
  }
}

async function exportQuantBacktestArtifact(runId, format = "jsonl") {
  if (!runId || !els.backtestSurface) return;
  const cleanFormat = String(format || "jsonl").toLowerCase();
  const keepLast = selectedQuantExportRetention();
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} ${cleanFormat.toUpperCase()} export is being prepared.`);
  try {
    const payload = { format: cleanFormat };
    if (keepLast > 0) payload.keep_last_exports = keepLast;
    const res = await fetch(API.quantBacktestExport(runId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = renderArtifactExportSummary(data);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Artifact export failed: ${err.message || err}`);
  }
}

function selectedQuantExportRetention() {
  const field = els.backtestSurface?.querySelector?.('[data-action="export-retention"]');
  const value = Number(field?.value || 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

async function loadQuantExportHistory(runId) {
  if (!runId || !els.backtestSurface) return;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} export history is loading.`);
  try {
    const res = await fetch(`${API.quantBacktestExports(runId)}?limit=20`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = renderArtifactExportHistory(data);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Export history failed: ${err.message || err}`);
  }
}

async function previewQuantExportCleanup(runId) {
  if (!runId || !els.backtestSurface) return;
  const keepLast = selectedQuantExportRetention() || 5;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} export cleanup preview is loading.`);
  try {
    const qs = new URLSearchParams({ keep_last_exports: String(keepLast) });
    const res = await fetch(`${API.quantBacktestExportCleanupPreview(runId)}?${qs.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = renderArtifactExportCleanupPlan(data);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Export cleanup preview failed: ${err.message || err}`);
  }
}

async function applyQuantExportCleanup(runId, keepLast = 5) {
  if (!runId || !els.backtestSurface) return;
  const resolvedKeepLast = Number(keepLast || selectedQuantExportRetention() || 5);
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} export cleanup is applying.`);
  try {
    const res = await fetch(API.quantBacktestExportCleanup(runId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keep_last_exports: resolvedKeepLast }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = renderArtifactExportCleanupPlan(data);
    loadQuantRunHistory(true);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Export cleanup failed: ${err.message || err}`);
  }
}

async function verifyQuantExport(runId, manifestPath = "") {
  if (!runId || !els.backtestSurface) return;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} export integrity is being verified.`);
  try {
    const payload = manifestPath ? { export_manifest_path: manifestPath } : {};
    const res = await fetch(API.quantBacktestExportVerify(runId), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.backtestSurface.innerHTML = renderArtifactExportVerification(data);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Export verification failed: ${err.message || err}`);
  }
}

async function runQuantFeaturePreview() {
  if (!els.quantFeatureSurface) return;
  const request = quantFeatureRequestFromControls();
  if (!request.tickers.length) {
    els.quantFeatureSurface.innerHTML = decisionEmpty("퀀트 랩 유니버스에 종목을 하나 이상 입력하세요.");
    return;
  }
  els.quantFeatureSurface.innerHTML = decisionEmpty(`${request.tickers.join(", ")} 팩터를 계산하는 중입니다.`);
  try {
    const res = await fetch(API.quantFeatures, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    state.lastFeatureResult = data;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const diagnostics = data.diagnostics || {};
    const status = data.status || "unknown";
    els.quantFeatureSurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
        <span>${escapeHtml(data.as_of || "알 수 없음")} · ${escapeHtml(request.benchmark)} 벤치마크 · 데이터 마트</span>
      </div>
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>종목</th><th>기준일</th><th>신선도</th><th>모멘텀</th><th>변동성</th><th>낙폭</th><th>추세</th><th>상대강도</th></tr></thead>
          <tbody>
            ${rows.map((row) => {
              const features = row.features || {};
              return `
                <tr>
                  <td>${escapeHtml(row.ticker || "")}</td>
                  <td>${escapeHtml(row.as_of || "알 수 없음")}</td>
                  <td><span class="table-status ${escapeHtml(decisionStatusClass(row.freshness_status))}">${escapeHtml(row.freshness_status || "알 수 없음")}</span></td>
                  <td>${escapeHtml(formatQuantValue(features.momentum_63d))}</td>
                  <td>${escapeHtml(formatQuantValue(features.realized_vol_21d))}</td>
                  <td>${escapeHtml(formatQuantValue(features.drawdown_current))}</td>
                  <td>${escapeHtml(formatQuantValue(features.ma_ratio_20_50))}</td>
                  <td>${escapeHtml(formatQuantValue(features.relative_strength_spy_63d))}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
      <div class="decision-chip-row">
        ${Object.entries(diagnostics.price_counts || {}).map(([ticker, count]) => `<span>${escapeHtml(ticker)} ${escapeHtml(_fmtNumber(count))}행</span>`).join("")}
      </div>
      ${renderFreshnessAuditPanel(diagnostics)}
      ${(diagnostics.missing_assets || []).length ? `<div class="decision-warning">누락 종목: ${escapeHtml(diagnostics.missing_assets.join(", "))}</div>` : ""}
      ${(diagnostics.stale_assets || []).length ? `<div class="decision-warning">오래된 가격: ${escapeHtml(diagnostics.stale_assets.join(", "))}</div>` : ""}
    `;
  } catch (err) {
    els.quantFeatureSurface.innerHTML = decisionEmpty(`팩터 미리보기 실패: ${err.message || err}`);
  }
}

function renderSignalDecisionBrief(rows, diagnostics, template) {
  const signals = rows.map((row) => Number(row.signal || 0));
  const active = signals.filter((value) => value > 0).length;
  const neutral = signals.filter((value) => value === 0).length;
  const negative = Math.max(0, rows.length - active - neutral);
  const scoreValues = rows.map((row) => Number(row.final_score)).filter(Number.isFinite);
  const avgScore = scoreValues.length
    ? scoreValues.reduce((sum, value) => sum + value, 0) / scoreValues.length
    : null;
  const execution = diagnostics.execution_assumption || "next_bar_close";
  const shift = diagnostics.signal_shift_bars ?? 1;
  const selected = rows
    .filter((row) => Number(row.signal || 0) > 0)
    .map((row) => row.ticker)
    .filter(Boolean)
    .join(", ");
  const decisionTone = active ? "ok" : "warn";
  return `
    <div class="decision-practical-grid signal-practical-grid">
      ${decisionMetric("전략 템플릿", quantTemplateLabel(template), "ok")}
      ${decisionMetric("매수 신호", `${active}/${rows.length}`, decisionTone)}
      ${decisionMetric("중립/제외", `${neutral + negative}`, neutral + negative ? "warn" : "ok")}
      ${decisionMetric("평균 점수", fmtDecimal(avgScore, 3), avgScore === null ? "warn" : "ok")}
      ${decisionMetric("체결 가정", execution === "next_bar_close" ? "다음 봉 종가" : execution, "ok")}
      ${decisionMetric("시그널 지연", `${shift}봉`, Number(shift) >= 1 ? "ok" : "fail")}
    </div>
    <div class="decision-summary ${decisionTone}">
      ${active
        ? `현재 조건에서는 ${escapeHtml(selected || "선정 종목")}에만 포지션을 부여합니다. 신호일과 체결일을 분리해 look-ahead를 피하고, 다음 백테스트/포트폴리오 입력으로 바로 검증하세요.`
        : "현재 조건에서는 매수 후보가 없습니다. 모멘텀 기간, Top N, 리서치 점수 사용 여부, 데이터 신선도 조건을 완화해 재검토하세요."}
    </div>
  `;
}

async function runQuantSignalPreview() {
  if (!els.quantSignalSurface) return;
  const base = quantFeatureRequestFromControls();
  const template = quantSignalTemplateFromStrategy(els.backtestStrategy?.value);
  if (!base.tickers.length) {
    els.quantSignalSurface.innerHTML = decisionEmpty("퀀트 랩 유니버스에 종목을 하나 이상 입력하세요.");
    return;
  }
  els.quantSignalSurface.innerHTML = decisionEmpty(`${base.tickers.join(", ")} 시그널을 생성하는 중입니다.`);
  try {
    const res = await fetch(API.quantSignals, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...base, template, use_research_score: !!els.backtestUseResearchScore?.checked }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    state.lastSignalResult = data;
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const diagnostics = data.diagnostics || {};
    const status = data.status || "unknown";
    els.quantSignalSurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
        <span>${escapeHtml(quantTemplateLabel(template))} · ${escapeHtml(diagnostics.execution_assumption || "next_bar_close")} · ${escapeHtml(String(diagnostics.signal_shift_bars || 1))}봉 지연</span>
      </div>
      ${renderSignalDecisionBrief(rows, diagnostics, template)}
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>종목</th><th>신호일</th><th>점수</th><th>신호</th><th>체결일</th><th>진단</th></tr></thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${escapeHtml(row.ticker || "")}</td>
                <td>${escapeHtml(row.date || "알 수 없음")}</td>
                <td>${escapeHtml(fmtDecimal(row.final_score, 3))}</td>
                <td><span class="table-status ${Number(row.signal || 0) > 0 ? "ok" : "warn"}">${escapeHtml(fmtDecimal(row.signal, 2))}</span></td>
                <td>${escapeHtml(row.execution_date || "다음 가용 봉")}</td>
                <td><div class="decision-chip-row compact">${renderDiagnosticsChips(row.diagnostics)}</div></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
      ${renderResearchProvenancePanel(diagnostics.research_score_provenance)}
      ${renderFreshnessAuditPanel(diagnostics)}
      ${(data.warnings || []).length ? `<div class="decision-warning">${escapeHtml(data.warnings.join(" "))}</div>` : ""}
    `;
  } catch (err) {
    els.quantSignalSurface.innerHTML = decisionEmpty(`시그널 생성 실패: ${err.message || err}`);
  }
}

function quantStrategyDraftFromControls() {
  const request = quantBacktestRequestFromControls();
  return {
    strategy_id: "custom_momentum_review_v1",
    name: "Custom Momentum Review",
    universe: request.tickers.length ? request.tickers : ["SPY", "QQQ", "TLT"],
    benchmark: request.benchmark || "SPY",
    frequency: "daily",
    features: {
      momentum_63d: { id: "momentum_63d", lookback: 63 },
      realized_vol_21d: { id: "realized_vol_21d", lookback: 21 },
      ...(request.use_research_score ? { research_score: { id: "research_score", max_age_days: 7 } } : {}),
    },
    signal: { type: "rank_top_n", top_n: request.top_n || 2 },
    portfolio: { method: request.portfolio_method || "equal_weight", max_weight: 0.5 },
    execution: {
      trade_at: "next_bar_close",
      transaction_cost_bps: request.transaction_cost_bps ?? 5,
      slippage_bps: request.slippage_bps ?? 2,
    },
    diagnostics: {
      freshness_profile: request.freshness_profile || "research_default",
      require_fresh_prices: !!request.require_fresh_prices,
      require_no_lookahead: true,
    },
  };
}

function setStrategyEditor(strategy) {
  if (!els.strategyDefinitionJson) return;
  els.strategyDefinitionJson.value = JSON.stringify(strategy || quantStrategyDraftFromControls(), null, 2);
  state.activeStrategyId = String(strategy?.strategy_id || "");
}

function strategyPayloadFromEditor() {
  const raw = els.strategyDefinitionJson?.value || "";
  if (!raw.trim()) return quantStrategyDraftFromControls();
  return JSON.parse(raw);
}

function applyStrategyToControls(strategy) {
  if (!strategy || typeof strategy !== "object") return;
  const universe = Array.isArray(strategy.universe) ? strategy.universe : [];
  if (universe.length && els.backtestTicker) setBacktestUniverse(universe);
  if (universe.length && els.portfolioTickers) els.portfolioTickers.value = universe.join(",");
  if (strategy.benchmark && els.portfolioBenchmark) els.portfolioBenchmark.value = strategy.benchmark;
  if (strategy.benchmark && els.backtestBenchmark) els.backtestBenchmark.value = strategy.benchmark;
  const portfolio = strategy.portfolio || {};
  if (portfolio.method && els.portfolioMethod) els.portfolioMethod.value = portfolio.method;
  if (portfolio.max_weight && els.portfolioMaxWeight) els.portfolioMaxWeight.value = String(portfolio.max_weight);
  const signal = strategy.signal || {};
  if (signal.top_n && els.backtestTopN) els.backtestTopN.value = String(signal.top_n);
  const execution = strategy.execution || {};
  if (execution.transaction_cost_bps !== undefined && els.backtestCostBps) {
    els.backtestCostBps.value = String(execution.transaction_cost_bps);
  }
  if (execution.slippage_bps !== undefined && els.backtestSlippageBps) {
    els.backtestSlippageBps.value = String(execution.slippage_bps);
  }
  const diagnostics = strategy.diagnostics || {};
  if (diagnostics.freshness_profile && els.backtestFreshnessProfile) {
    els.backtestFreshnessProfile.value = diagnostics.freshness_profile;
  }
  if (els.backtestRequireFresh && diagnostics.require_fresh_prices !== undefined) {
    els.backtestRequireFresh.checked = !!diagnostics.require_fresh_prices;
  }
  if (els.backtestUseResearchScore) {
    const features = strategy.features || {};
    els.backtestUseResearchScore.checked = !!features.research_score;
  }
  if (els.backtestStrategy) {
    const hasResearchScore = !!(strategy.features || {}).research_score;
    els.backtestStrategy.value = hasResearchScore
      ? "research_confirmed_momentum"
      : signal.type === "rank_top_n"
        ? "momentum_ranking"
        : "moving_average";
  }
  state.activeStrategyId = String(strategy.strategy_id || "");
  if (els.backtestStrategyRegistry) {
    populateBacktestStrategyRegistry();
    els.backtestStrategyRegistry.value = state.activeStrategyId;
  }
}

function populateBacktestStrategyRegistry() {
  if (!els.backtestStrategyRegistry) return;
  const items = Array.isArray(state.quantStrategyItems) ? state.quantStrategyItems : [];
  const selected = state.activeStrategyId || els.backtestStrategyRegistry.value || "";
  els.backtestStrategyRegistry.innerHTML = `
    <option value="">전략 거버넌스 선택</option>
    ${items.map((item) => {
      const id = item.strategy_id || "";
      const label = item.name || id;
      const source = item.source || "default";
      return `<option value="${escapeHtml(id)}">${escapeHtml(label)} · ${escapeHtml(source)}</option>`;
    }).join("")}
  `;
  if (selected && items.some((item) => item.strategy_id === selected)) {
    els.backtestStrategyRegistry.value = selected;
  }
}

function renderQuantStrategyList(extraHtml = "") {
  if (!els.quantStrategySurface) return;
  const items = Array.isArray(state.quantStrategyItems) ? state.quantStrategyItems : [];
  populateBacktestStrategyRegistry();
  if (!items.length) {
    els.quantStrategySurface.innerHTML = decisionEmpty("아직 사용할 수 있는 전략 정의가 없습니다.");
    return;
  }
  els.quantStrategySurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ok">성공</span>
      <span>${escapeHtml(_fmtNumber(items.length))}개 전략 · 다음 봉 체결 필수</span>
    </div>
    ${extraHtml}
    <div class="decision-table-wrap">
      <table class="decision-table">
        <thead><tr><th>전략</th><th>출처</th><th>버전</th><th>체결</th><th>팩터</th><th>작업</th></tr></thead>
        <tbody>
          ${items.map((item) => {
            const features = item.features && typeof item.features === "object" ? Object.keys(item.features) : [];
            const execution = item.execution || {};
            const source = item.source || "default";
            const strategyId = item.strategy_id || "";
            return `
              <tr>
                <td>${escapeHtml(item.name || strategyId)}</td>
                <td>${escapeHtml(source)}</td>
                <td>${escapeHtml(`${item.schema_version || "default"} / ${item.strategy_version || "-"}`)}</td>
                <td><span class="table-status ${execution.trade_at === "next_bar_close" ? "ok" : "fail"}">${escapeHtml(execution.trade_at || "-")}</span></td>
                <td>${escapeHtml(features.join(", ") || "-")}</td>
                <td>
                  <button type="button" class="linkish" data-strategy-load="${escapeHtml(strategyId)}">불러오기</button>
                  <button type="button" class="linkish" data-strategy-dry="${escapeHtml(strategyId)}">검증</button>
                  ${source === "user" ? `<button type="button" class="linkish" data-strategy-delete="${escapeHtml(strategyId)}">삭제</button>` : ""}
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
  els.quantStrategySurface.querySelectorAll("[data-strategy-load]").forEach((button) => {
    button.addEventListener("click", () => loadQuantStrategyDetail(button.dataset.strategyLoad || ""));
  });
  els.quantStrategySurface.querySelectorAll("[data-strategy-dry]").forEach((button) => {
    button.addEventListener("click", async () => {
      const strategy = await fetchQuantStrategy(button.dataset.strategyDry || "");
      if (strategy) {
        setStrategyEditor(strategy);
        applyStrategyToControls(strategy);
        runQuantStrategyDryRun(strategy);
      }
    });
  });
  els.quantStrategySurface.querySelectorAll("[data-strategy-delete]").forEach((button) => {
    button.addEventListener("click", () => deleteQuantStrategy(button.dataset.strategyDelete || ""));
  });
}

function renderQuantStrategyResult(data) {
  if (!els.quantStrategyResultSurface) return;
  const diagnostics = data.diagnostics || {};
  const status = data.status || "unknown";
  const strategy = data.strategy || {};
  els.quantStrategyResultSurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
      <span>${escapeHtml(strategy.strategy_id || state.activeStrategyId || "strategy")} · valid ${data.valid ? "yes" : "no"}</span>
    </div>
    <div class="decision-chip-row">
      <span>trade_at ${escapeHtml(diagnostics.execution_trade_at || "-")}</span>
      <span>lookahead ${diagnostics.lookahead_safe ? "safe" : "check"}</span>
      <span>schema ${escapeHtml(diagnostics.schema_version || strategy.schema_version || "-")}</span>
      <span>version ${escapeHtml(diagnostics.strategy_version || strategy.strategy_version || "-")}</span>
      ${(diagnostics.feature_ids || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
    </div>
    ${(diagnostics.migration_history || []).length ? `<div class="decision-warning">Migrated strategy schema: ${escapeHtml(diagnostics.migration_history.map((item) => item.migration || item.to_schema_version || "migration").join(", "))}</div>` : ""}
    ${(diagnostics.missing_features || []).length ? `<div class="decision-warning">Missing features: ${escapeHtml(diagnostics.missing_features.join(", "))}</div>` : ""}
    ${(data.warnings || []).length ? `<div class="decision-warning">${escapeHtml(data.warnings.join(" "))}</div>` : ""}
  `;
}

async function loadQuantStrategies(force = false) {
  if (!els.quantStrategySurface || (state.quantStrategiesLoaded && !force)) return;
  els.quantStrategySurface.innerHTML = decisionEmpty("Loading strategy registry.");
  try {
    const res = await fetch(API.quantStrategies);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    state.quantStrategyItems = Array.isArray(data.items) ? data.items : [];
    state.quantStrategiesLoaded = true;
    renderQuantStrategyList();
    if (!els.strategyDefinitionJson?.value.trim()) {
      setStrategyEditor(state.quantStrategyItems[0] || quantStrategyDraftFromControls());
    }
  } catch (err) {
    els.quantStrategySurface.innerHTML = decisionEmpty(`Strategy registry failed: ${err.message || err}`);
  }
}

async function fetchQuantStrategy(strategyId) {
  if (!strategyId) return null;
  const res = await fetch(API.quantStrategy(strategyId));
  const data = await res.json();
  if (!res.ok) {
    showQuantStrategyMessage(`Strategy load failed: ${data.detail || `HTTP ${res.status}`}`, "failed");
    return null;
  }
  return data;
}

async function loadQuantStrategyDetail(strategyId) {
  const strategy = await fetchQuantStrategy(strategyId);
  if (!strategy) return;
  setStrategyEditor(strategy);
  applyStrategyToControls(strategy);
  populateBacktestStrategyRegistry();
  showQuantStrategyMessage(`${strategy.strategy_id || "strategy"} loaded into the workbench controls.`, "success");
}

async function runQuantStrategyDryRun(strategy = null) {
  if (!els.quantStrategyResultSurface) return;
  let payload = strategy;
  try {
    payload = payload || strategyPayloadFromEditor();
  } catch (err) {
    showQuantStrategyMessage(`Strategy JSON is invalid: ${err.message || err}`, "failed");
    return;
  }
  els.quantStrategyResultSurface.innerHTML = decisionEmpty("Strategy dry-run is checking features and execution policy.");
  try {
    const res = await fetch(API.quantStrategyDryRun, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.strategy) {
      setStrategyEditor(data.strategy);
      applyStrategyToControls(data.strategy);
    }
    renderQuantStrategyResult(data);
  } catch (err) {
    showQuantStrategyMessage(`Strategy dry-run failed: ${err.message || err}`, "failed");
  }
}

async function saveQuantStrategy() {
  let payload;
  try {
    payload = strategyPayloadFromEditor();
  } catch (err) {
    showQuantStrategyMessage(`Strategy JSON is invalid: ${err.message || err}`, "failed");
    return;
  }
  els.quantStrategyResultSurface.innerHTML = decisionEmpty("Saving strategy definition.");
  try {
    const res = await fetch(API.quantStrategySave, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (data.strategy) setStrategyEditor(data.strategy);
    showQuantStrategyMessage(`Saved ${data.strategy?.strategy_id || payload.strategy_id}.`, "success");
    state.quantStrategiesLoaded = false;
    await loadQuantStrategies(true);
  } catch (err) {
    showQuantStrategyMessage(`Strategy save failed: ${err.message || err}`, "failed");
  }
}

async function deleteQuantStrategy(strategyId = "") {
  let id = strategyId || state.activeStrategyId || "";
  try {
    if (!id) id = strategyPayloadFromEditor().strategy_id || "";
    if (!id) {
      showQuantStrategyMessage("No saved strategy id is selected.", "failed");
      return;
    }
    const res = await fetch(API.quantStrategy(id), { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    showQuantStrategyMessage(`Deleted ${data.strategy_id || id}.`, "success");
    setStrategyEditor(quantStrategyDraftFromControls());
    state.quantStrategiesLoaded = false;
    await loadQuantStrategies(true);
  } catch (err) {
    showQuantStrategyMessage(`Strategy delete failed: ${err.message || err}`, "failed");
  }
}

function showQuantStrategyMessage(message, status = "success") {
  if (!els.quantStrategyResultSurface) return;
  els.quantStrategyResultSurface.innerHTML = `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
      <span>${escapeHtml(message)}</span>
    </div>
  `;
}

async function runHomeBacktest() {
  if (!els.backtestSurface || !els.backtestTicker) return;
  const legacyRequest = backtestRequestFromControls();
  const request = quantBacktestRequestFromControls();
  if (!request.tickers.length) {
    els.backtestSurface.innerHTML = decisionEmpty("백테스트할 티커를 하나 이상 입력해야 합니다.");
    return;
  }
  state.lastBacktestRequest = legacyRequest;
  state.lastQuantBacktestRequest = request;
  els.backtestSurface.innerHTML = decisionEmpty(`${request.tickers.join(", ")} 백테스트를 실행 중입니다.`);
  try {
    const res = await fetch(API.quantBacktest, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const enriched = await attachBenchmarkComparison(data, { ...request, ...legacyRequest });
    state.lastBacktestResult = enriched;
    syncPortfolioFromBacktest();
    renderQuantBacktestResult(enriched, { ...request, ...legacyRequest });
    loadQuantRunHistory(true);
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Backtest failed: ${err.message || err}`);
  }
}

function normalizeQuantBundle(bundle) {
  const config = bundle.config || {};
  const manifest = bundle.manifest || {};
  const files = manifest.files || {};
  return {
    status: bundle.status || "success",
    run_id: bundle.run_id || manifest.run_id || "",
    template: config.template || "unknown",
    tickers: config.tickers || [],
    benchmark: config.benchmark || "",
    date_range: {
      start: config.start_date || "",
      end: config.end_date || "",
    },
    metrics: bundle.metrics || {},
    equity_curve: Array.isArray(bundle.equity_curve) ? bundle.equity_curve : [],
    drawdown_curve: Array.isArray(bundle.drawdown_curve) ? bundle.drawdown_curve : [],
    trades: Array.isArray(bundle.trades) ? bundle.trades : [],
    signals: Array.isArray(bundle.signals) ? bundle.signals : [],
    weights: Array.isArray(bundle.weights) ? bundle.weights : [],
    diagnostics: bundle.diagnostics || {},
    artifacts: files,
    replay_reports: bundle.replay_reports || {},
    config,
  };
}

async function loadQuantBacktestArtifact(runId) {
  if (!runId || !els.backtestSurface) return;
  els.backtestSurface.innerHTML = decisionEmpty(`${runId} artifact bundle is loading.`);
  try {
    const res = await fetch(API.quantBacktestBundle(runId));
    const bundle = await res.json();
    if (!res.ok) throw new Error(bundle.detail || `HTTP ${res.status}`);
    const data = normalizeQuantBundle(bundle);
    const artifactRequest = {
      ...(data.config || {}),
      benchmark: data.config?.benchmark || els.backtestBenchmark?.value || "SPY",
      compare_benchmark: !!els.backtestBenchmarkCompare?.checked,
    };
    const enriched = await attachBenchmarkComparison(data, artifactRequest);
    state.lastBacktestResult = enriched;
    state.lastQuantBacktestRequest = artifactRequest;
    state.lastBacktestRequest = artifactRequest;
    renderQuantBacktestResult(enriched, artifactRequest);
    syncPortfolioFromBacktest();
  } catch (err) {
    els.backtestSurface.innerHTML = decisionEmpty(`Artifact load failed: ${err.message || err}`);
  }
}

function renderQuantExportStorageReport(data) {
  const topRuns = Array.isArray(data.top_runs) ? data.top_runs : [];
  const staleExports = Array.isArray(data.stale_exports) ? data.stale_exports : [];
  const formatCounts = data.format_counts || {};
  const manifestStatuses = data.manifest_status_counts || {};
  const formatText = Object.keys(formatCounts).length
    ? Object.entries(formatCounts).map(([key, value]) => `${key}:${_fmtNumber(value)}`).join(", ")
    : "none";
  const manifestText = Object.keys(manifestStatuses).length
    ? Object.entries(manifestStatuses).map(([key, value]) => `${key}:${_fmtNumber(value)}`).join(", ")
    : "none";
  return `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status || "success"))}">${escapeHtml(data.status || "success")}</span>
      <span>cross-run export storage report</span>
    </div>
    <div class="decision-chip-row">
      <span>runs ${escapeHtml(_fmtNumber(data.run_count || 0))}</span>
      <span>with exports ${escapeHtml(_fmtNumber(data.runs_with_exports || 0))}</span>
      <span>export dirs ${escapeHtml(_fmtNumber(data.export_directory_count || 0))}</span>
      <span>bytes ${escapeHtml(_fmtNumber(data.total_bytes || 0))}</span>
      <span>stale ${escapeHtml(_fmtNumber(data.stale_export_count || 0))}</span>
      <button type="button" class="linkish decision-inline-action" data-action="cross-run-cleanup-preview" data-keep-last="1" data-stale-after-days="0">cleanup preview</button>
    </div>
    <div class="decision-list compact">
      <div class="decision-list-row"><span>Formats</span><strong>${escapeHtml(formatText)}</strong></div>
      <div class="decision-list-row"><span>Manifest status</span><strong>${escapeHtml(manifestText)}</strong></div>
      <div class="decision-list-row"><span>Oldest export</span><strong>${escapeHtml(data.oldest_export_generated_at || "-")}</strong></div>
      <div class="decision-list-row"><span>Newest export</span><strong>${escapeHtml(data.newest_export_generated_at || "-")}</strong></div>
      <div class="decision-list-row"><span>Root</span><strong>${escapeHtml(compactArtifactPath(data.artifact_root || ""))}</strong></div>
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
                <td>${escapeHtml(_fmtNumber(item.export_count || 0))}</td>
                <td>${escapeHtml(_fmtNumber(item.total_bytes || 0))}</td>
                <td>${escapeHtml(_fmtNumber(item.total_rows || 0))}</td>
                <td>${escapeHtml(Object.keys(item.formats || {}).join(", ") || "-")}</td>
                <td>${escapeHtml(fmtDate(item.newest_export_generated_at || ""))}</td>
                <td><button type="button" class="linkish" data-quant-run-id="${escapeHtml(item.run_id || "")}">open</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    ` : decisionEmpty("No generated artifact exports are present yet.")}
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
                <td>${escapeHtml(_fmtNumber(item.age_days || 0))}d</td>
                <td>${escapeHtml(_fmtNumber(item.total_bytes || 0))}</td>
                <td><span class="table-status ${escapeHtml(decisionStatusClass(item.status || "unknown"))}">${escapeHtml(item.status || "unknown")}</span></td>
                <td>${escapeHtml(compactArtifactPath(item.manifest_path || ""))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    ` : decisionEmpty("No export directories exceed the stale-age threshold.")}
  `;
}

function renderCrossRunExportCleanupPlan(data) {
  const candidates = Array.isArray(data.candidates) ? data.candidates : [];
  const pruned = Array.isArray(data.pruned_exports) ? data.pruned_exports : [];
  const applied = !!data.cleanup_applied;
  const shown = applied ? pruned : candidates;
  if (!applied) {
    state.lastCrossRunExportCleanupPreview = data;
  }
  return `
    <div class="decision-status-row">
      <span class="decision-badge ${escapeHtml(decisionStatusClass(data.status || "success"))}">${escapeHtml(data.status || "success")}</span>
      <span>cross-run export cleanup ${applied ? "applied" : "preview"}</span>
    </div>
    <div class="decision-chip-row">
      <span>keep last ${escapeHtml(_fmtNumber(data.keep_last_exports || 0))}</span>
      <span>stale ${escapeHtml(_fmtNumber(data.stale_after_days || 0))}d</span>
      <span>eligible ${escapeHtml(_fmtNumber(data.eligible_export_count || 0))}</span>
      <span>candidates ${escapeHtml(_fmtNumber(data.candidate_count || 0))}</span>
      <span>bytes ${escapeHtml(_fmtNumber(applied ? data.total_bytes_pruned || 0 : data.total_bytes_to_prune || 0))}</span>
      <span>preview ${escapeHtml(String(data.preview_id || "").slice(0, 12))}</span>
    </div>
    ${!applied && candidates.length ? `
      <div class="decision-chip-row">
        <button type="button" class="linkish decision-inline-action danger" data-action="cross-run-cleanup-apply">apply exact preview</button>
      </div>
    ` : ""}
    ${shown.length ? `
      <div class="decision-section-title">${applied ? "Pruned exports" : "Exports that would be pruned"}</div>
      ${renderArtifactExportCleanupTable(shown)}
    ` : decisionEmpty("No cross-run export directories match this cleanup policy.")}
  `;
}

async function previewCrossRunExportCleanup(keepLast = 1, staleAfterDays = 0) {
  if (!els.quantRunHistorySurface) return;
  const params = new URLSearchParams({
    keep_last_exports: String(keepLast || 1),
    stale_after_days: String(staleAfterDays ?? 0),
    limit: "50",
  });
  els.quantRunHistorySurface.innerHTML = decisionEmpty("Loading cross-run export cleanup preview.");
  try {
    const res = await fetch(`${API.quantExportCleanupPreview}?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.quantRunHistorySurface.innerHTML = renderCrossRunExportCleanupPlan(data);
  } catch (err) {
    els.quantRunHistorySurface.innerHTML = decisionEmpty(`Cross-run export cleanup preview failed: ${err.message || err}`);
  }
}

async function applyCrossRunExportCleanup() {
  if (!els.quantRunHistorySurface) return;
  const preview = state.lastCrossRunExportCleanupPreview || {};
  const candidateIds = Array.isArray(preview.candidate_ids) ? preview.candidate_ids : [];
  els.quantRunHistorySurface.innerHTML = decisionEmpty("Applying exact cross-run export cleanup preview.");
  try {
    const res = await fetch(API.quantExportCleanup, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preview_id: preview.preview_id || "",
        candidate_ids: candidateIds,
        keep_last_exports: preview.keep_last_exports || 1,
        stale_after_days: preview.stale_after_days ?? 0,
        limit: preview.limit || 50,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    state.lastCrossRunExportCleanupPreview = null;
    els.quantRunHistorySurface.innerHTML = renderCrossRunExportCleanupPlan(data);
  } catch (err) {
    els.quantRunHistorySurface.innerHTML = decisionEmpty(`Cross-run export cleanup failed: ${err.message || err}`);
  }
}

async function loadQuantExportStorageReport() {
  if (!els.quantRunHistorySurface) return;
  els.quantRunHistorySurface.innerHTML = decisionEmpty("Loading cross-run export storage report.");
  try {
    const res = await fetch(`${API.quantExportStorage}?limit=20&stale_after_days=30`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    els.quantRunHistorySurface.innerHTML = renderQuantExportStorageReport(data);
    els.quantRunHistorySurface.querySelectorAll("[data-quant-run-id]").forEach((button) => {
      button.addEventListener("click", () => loadQuantBacktestArtifact(button.dataset.quantRunId || ""));
    });
  } catch (err) {
    els.quantRunHistorySurface.innerHTML = decisionEmpty(`Export storage report failed: ${err.message || err}`);
  }
}

async function loadQuantRunHistory(force = false) {
  if (!els.quantRunHistorySurface || (state.quantRunHistoryLoaded && !force)) return;
  els.quantRunHistorySurface.innerHTML = decisionEmpty("퀀트 랩 산출물 이력을 불러오는 중입니다.");
  try {
    const res = await fetch(`${API.quantBacktests}?limit=8`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const items = Array.isArray(data.items) ? data.items : [];
    state.quantRunHistoryLoaded = true;
    if (!items.length) {
      els.quantRunHistorySurface.innerHTML = decisionEmpty("아직 저장된 퀀트 랩 백테스트 산출물이 없습니다.");
      return;
    }
    els.quantRunHistorySurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ok">${escapeHtml(data.status || "success")}</span>
        <span>${escapeHtml(_fmtNumber(data.count))} saved runs</span>
      </div>
      <div class="decision-table-wrap">
        <table class="decision-table">
          <thead><tr><th>Run</th><th>Template</th><th>Universe</th><th>Sharpe</th><th>MDD</th><th>Lookahead</th><th>Reports</th><th>Open</th><th>Replay</th><th>Export</th></tr></thead>
          <tbody>
            ${items.map((item) => {
              const metrics = item.metrics || {};
              const diagnostics = item.diagnostics || {};
              return `
                <tr>
                  <td>${escapeHtml(item.run_id || "")}</td>
                  <td>${escapeHtml(item.template || "")}</td>
                  <td>${escapeHtml((item.tickers || []).join(","))}</td>
                  <td>${escapeHtml(fmtDecimal(metrics.sharpe, 2))}</td>
                  <td>${escapeHtml(fmtMetricRatio(metrics.max_drawdown))}</td>
                  <td><span class="table-status ${diagnostics.lookahead_safe ? "ok" : "fail"}">${diagnostics.lookahead_safe ? "safe" : "check"}</span></td>
                  <td><button type="button" class="linkish" data-quant-replay-reports-id="${escapeHtml(item.run_id || "")}">${escapeHtml(_fmtNumber(item.replay_reports?.count || 0))}</button></td>
                  <td><button type="button" class="linkish" data-quant-run-id="${escapeHtml(item.run_id || "")}">open</button></td>
                  <td><button type="button" class="linkish" data-quant-replay-id="${escapeHtml(item.run_id || "")}">compare</button></td>
                  <td>
                    <button type="button" class="linkish" data-quant-export-id="${escapeHtml(item.run_id || "")}" data-format="jsonl">jsonl</button>
                    <button type="button" class="linkish" data-quant-export-id="${escapeHtml(item.run_id || "")}" data-format="parquet">parquet</button>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
      <div class="decision-chip-row">
        ${items.slice(0, 3).map((item) => `<span>${escapeHtml(fmtDate(item.generated_at))} · ${escapeHtml(compactArtifactPath(item.manifest))}</span>`).join("")}
      </div>
    `;
    els.quantRunHistorySurface.querySelectorAll("[data-quant-run-id]").forEach((button) => {
      button.addEventListener("click", () => loadQuantBacktestArtifact(button.dataset.quantRunId || ""));
    });
    els.quantRunHistorySurface.querySelectorAll("[data-quant-replay-id]").forEach((button) => {
      button.addEventListener("click", () => runQuantBacktestReplay(button.dataset.quantReplayId || ""));
    });
    els.quantRunHistorySurface.querySelectorAll("[data-quant-replay-reports-id]").forEach((button) => {
      button.addEventListener("click", () => loadQuantReplayReports(button.dataset.quantReplayReportsId || ""));
    });
    els.quantRunHistorySurface.querySelectorAll("[data-quant-export-id]").forEach((button) => {
      button.addEventListener("click", () => exportQuantBacktestArtifact(button.dataset.quantExportId || "", button.dataset.format || "jsonl"));
    });
  } catch (err) {
    els.quantRunHistorySurface.innerHTML = decisionEmpty(`실행 이력 로드 실패: ${err.message || err}`);
  }
}

async function runPortfolioOptimize() {
  if (!els.portfolioSurface || !els.portfolioTickers) return;
  const tickers = parseTickerInput(els.portfolioTickers.value || "");
  if (!tickers.length) {
    els.portfolioSurface.innerHTML = decisionEmpty("최적화할 티커를 하나 이상 입력해야 합니다.");
    return;
  }
  const startDate = textInputValue(els.portfolioStartDate);
  const endDate = textInputValue(els.portfolioEndDate);
  const lookbackDays = numberInputValue(els.portfolioLookbackDays, 756, { min: 2, max: 5000 });
  const maxWeight = numberInputValue(els.portfolioMaxWeight, 0.6, { min: 0.01, max: 1 });
  const benchmark = normalizeTickerToken(els.portfolioBenchmark?.value || "SPY") || "SPY";
  const covarianceMethod = els.portfolioCovarianceMethod?.value || "sample";
  const shrinkageAlpha = numberInputValue(els.portfolioShrinkageAlpha, 0.1, { min: 0, max: 1 });
  els.portfolioSurface.innerHTML = decisionEmpty(`${tickers.join(", ")} 포트폴리오 최적화를 실행 중입니다.`);
  try {
    const res = await fetch(API.portfolioOptimize, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tickers,
        method: els.portfolioMethod?.value || "equal_weight",
        benchmark,
        start_date: startDate,
        end_date: endDate,
        lookback_days: lookbackDays,
        max_weight: maxWeight,
        covariance_method: covarianceMethod,
        shrinkage_alpha: shrinkageAlpha,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    const weights = data.weights || {};
    const entries = Object.entries(weights).sort((a, b) => Number(b[1]) - Number(a[1]));
    const status = data.status || "unknown";
    const diagnostics = data.diagnostics || {};
    const returnCounts = data.return_counts || {};
    const portfolioMetrics = data.portfolio_metrics || {};
    const riskContributions = data.risk_contributions || {};
    const correlationMatrix = data.correlation_matrix || {};
    els.portfolioSurface.innerHTML = `
      <div class="decision-status-row">
        <span class="decision-badge ${escapeHtml(decisionStatusClass(status))}">${escapeHtml(decisionStatusLabel(status))}</span>
        <span>${escapeHtml(portfolioMethodLabel(data.method || ""))} · ${escapeHtml(data.benchmark || benchmark)} 벤치마크 · 비중 합계 ${escapeHtml(String(data.sum_weights ?? "-"))}</span>
      </div>
      <div class="decision-summary ok">
        ${escapeHtml(tickers.join(", "))} · ${escapeHtml(startDate || "조회 기간")} -> ${escapeHtml(endDate || "최근")} · ${escapeHtml(String(lookbackDays))}일 가격 기준
      </div>
      ${renderPortfolioDecisionBrief({
        entries,
        portfolioMetrics,
        diagnostics,
        riskContributions,
        method: data.method || els.portfolioMethod?.value,
        benchmark: data.benchmark || benchmark,
        maxWeight,
      })}
      <div class="portfolio-weight-list">
        ${entries.length ? entries.map(([ticker, weight]) => `
          <div class="portfolio-weight-row">
            <span>${escapeHtml(ticker)}</span>
            <div><i style="width:${Math.max(2, Math.min(100, Number(weight) * 100))}%"></i></div>
            <strong>${escapeHtml(fmtPct(Number(weight) * 100))}</strong>
          </div>
        `).join("") : '<div class="muted small">No weights available.</div>'}
      </div>
      <div class="decision-metric-grid dense">
        ${decisionMetric("자산 수", _fmtNumber(diagnostics.asset_count || entries.length), status)}
        ${decisionMetric("최대 비중", fmtPct(Number(data.max_weight || maxWeight) * 100), status)}
        ${decisionMetric("최소 비중", entries.length ? fmtPct(Math.min(...entries.map(([, weight]) => Number(weight))) * 100) : "-", status)}
        ${decisionMetric("수익률 샘플", _fmtNumber(Object.values(returnCounts).reduce((sum, value) => sum + Number(value || 0), 0)), status)}
        ${decisionMetric("기대수익", fmtMetricRatio(portfolioMetrics.expected_annual_return), status)}
        ${decisionMetric("예상 변동성", fmtMetricRatio(portfolioMetrics.annualized_volatility), status)}
        ${decisionMetric("예상 Sharpe", fmtDecimal(portfolioMetrics.sharpe, 2), status)}
        ${decisionMetric("Active return", fmtMetricRatio(portfolioMetrics.active_annual_return), status)}
        ${decisionMetric("Tracking error", fmtMetricRatio(portfolioMetrics.tracking_error), status)}
        ${decisionMetric("Info ratio", fmtDecimal(portfolioMetrics.information_ratio, 2), status)}
        ${decisionMetric("베타", fmtDecimal(portfolioMetrics.beta_to_benchmark, 2), status)}
        ${decisionMetric("공분산", `${diagnostics.covariance_method || "sample"}${diagnostics.covariance_shrinkage_used ? ` ${fmtDecimal(diagnostics.shrinkage_alpha, 2)}` : ""}`, diagnostics.uses_covariance ? "ok" : "warn")}
        ${decisionMetric("효과 포지션", fmtDecimal(diagnostics.effective_number_of_positions, 2), status)}
      </div>
      ${Object.keys(riskContributions).length ? `
        <div class="decision-section-title">위험 기여도</div>
        ${renderRiskContributionBars(riskContributions)}
      ` : ""}
      ${renderCorrelationPreview(correlationMatrix)}
      ${Object.keys(returnCounts).length ? `
        <div class="decision-section-title">데이터 사용량</div>
        <div class="decision-chip-row">
          ${Object.entries(returnCounts).map(([ticker, count]) => `<span>${escapeHtml(ticker)} ${escapeHtml(_fmtNumber(count))}개 수익률</span>`).join("")}
        </div>
      ` : ""}
      ${(data.missing_assets || []).length ? `<div class="decision-warning">누락 데이터: ${escapeHtml(data.missing_assets.join(", "))}</div>` : ""}
      ${(data.warnings || []).length ? `<div class="decision-warning">${escapeHtml(data.warnings.join(" "))}</div>` : ""}
    `;
  } catch (err) {
    els.portfolioSurface.innerHTML = decisionEmpty(`포트폴리오 최적화 실패: ${err.message || err}`);
  }
}

const NEWS_CATEGORY_LABELS = {
  all: "전체",
  equity_index: "주식/지수",
  rates_credit: "금리/신용",
  macro_policy: "매크로",
  ai_semis: "AI/반도체",
  earnings: "실적",
  commodity: "원자재",
  crypto: "크립토",
  market: "기타",
};

function renderNewsCategories(items) {
  if (!els.homeNewsCategories) return;
  const counts = items.reduce((acc, item) => {
    const key = item.category || "market";
    acc[key] = (acc[key] || 0) + 1;
    acc.all = (acc.all || 0) + 1;
    return acc;
  }, {});
  const order = ["all", "equity_index", "macro_policy", "rates_credit", "ai_semis", "earnings", "commodity", "crypto", "market"];
  if (!counts[state.dashboardNewsCategory]) state.dashboardNewsCategory = "all";
  els.homeNewsCategories.innerHTML = order
    .filter((key) => counts[key])
    .map((key) => `
      <button type="button" class="news-category-chip ${state.dashboardNewsCategory === key ? "active" : ""}" data-category="${escapeHtml(key)}">
        ${escapeHtml(NEWS_CATEGORY_LABELS[key] || key)} <span>${counts[key]}</span>
      </button>
    `).join("");
  els.homeNewsCategories.querySelectorAll(".news-category-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.dashboardNewsCategory = btn.dataset.category || "all";
      renderDashboardNews();
    });
  });
}

function renderDashboardNews() {
  if (!els.homeNewsList) return;
  const category = state.dashboardNewsCategory || "all";
  const items = category === "all"
    ? state.dashboardNewsItems
    : state.dashboardNewsItems.filter((item) => (item.category || "market") === category);
  renderNewsCategories(state.dashboardNewsItems);
  if (!items.length) {
    els.homeNewsList.innerHTML = '<div class="home-news-empty">선택한 카테고리에 표시할 뉴스가 없습니다.</div>';
    return;
  }
  els.homeNewsList.innerHTML = items.slice(0, 20).map((item) => {
    const date = item.published_at ? fmtDate(item.published_at) : (item.collected_at ? fmtDate(item.collected_at) : "");
    const href = item.url ? `href="${escapeHtml(item.url)}" target="_blank" rel="noopener"` : "";
    const categoryLabel = NEWS_CATEGORY_LABELS[item.category || "market"] || item.category || "기타";
    const sourceTier = Number(item.source_tier);
    const sourceClass = sourceTier === 0 ? "major" : (sourceTier >= 3 ? "low" : "");
    return `
      <article class="home-news-card">
        <div class="home-news-meta">
          <span>${escapeHtml(categoryLabel)}</span>
          <span>${escapeHtml(item.symbol || "MARKET")}</span>
          <span class="news-source ${sourceClass}">${escapeHtml(item.source || "")}</span>
          <span>${escapeHtml(date)}</span>
        </div>
        <a ${href} class="home-news-title">${escapeHtml(item.title || "Untitled")}</a>
      </article>
    `;
  }).join("");
}

async function loadDashboardNews(force = false) {
  if (!els.homeNewsList || (state.dashboardLoaded && !force)) return;
  els.homeNewsList.innerHTML = '<div class="home-news-empty">뉴스를 불러오는 중입니다.</div>';
  try {
    const res = await fetch(API.dashboardNews);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      els.homeNewsList.innerHTML = '<div class="home-news-empty">표시할 최신 뉴스가 없습니다.</div>';
      state.dashboardNewsItems = [];
      renderNewsCategories([]);
      state.dashboardLoaded = true;
      return;
    }
    state.dashboardNewsItems = items;
    renderDashboardNews();
    state.dashboardLoaded = true;
  } catch (err) {
    els.homeNewsList.innerHTML = `<div class="home-news-empty">뉴스 로드 실패: ${escapeHtml(err.message || err)}</div>`;
  }
}

// ---------- History (server-persisted via /api/v1/runs) ----------
async function fetchHistory(ticker) {
  try {
    const qs = new URLSearchParams({ limit: "40" });
    if (ticker) qs.set("ticker", ticker);
    const res = await fetch(`${API.runs}?${qs.toString()}`);
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data.items) ? data.items : [];
  } catch {
    return [];
  }
}

async function renderHistory(filterTicker = null) {
  const items = await fetchHistory(filterTicker);
  els.historyList.innerHTML = "";
  if (els.historySummary) {
    els.historySummary.textContent = items.length ? `${items.length} runs` : "";
  }
  if (els.historyToggleBtn) {
    els.historyToggleBtn.classList.toggle("hidden", items.length <= 5);
    els.historyToggleBtn.textContent = state.historyExpanded ? "접기" : "펼치기";
  }
  if (!items.length) {
    els.historyList.innerHTML = '<li class="history-empty">아직 실행된 분석이 없습니다.</li>';
    return;
  }
  const visibleItems = state.historyExpanded ? items.slice(0, 40) : items.slice(0, 5);
  visibleItems.forEach((item) => {
    const li = document.createElement("li");
    li.className = "history-item";
    const statusCls = statusClass(item.status);
    const whenLocal = item.created_at ? new Date(item.created_at).toLocaleString() : "";
    li.innerHTML = `
      <span class="hi-ticker">${escapeHtml(item.ticker)}</span>
      <span class="hi-time">${escapeHtml(whenLocal)}</span>
      <span class="hi-status ${statusCls}">${escapeHtml(item.status || "")}</span>
    `;
    li.title = item.question || "";
    li.dataset.runId = item.id;
    li.addEventListener("click", () => loadRun(item.id));
    els.historyList.appendChild(li);
  });
  if (!state.historyExpanded && items.length > visibleItems.length) {
    const li = document.createElement("li");
    li.className = "history-more";
    li.textContent = `최근 5개만 표시 중 · ${items.length - visibleItems.length}개 더 있음`;
    els.historyList.appendChild(li);
  }
}

async function loadRun(runId) {
  try {
    const res = await fetch(API.run(runId));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const art = data.artifacts || {};
    if (art.response) {
      renderResponse(art.response, art.collection || null, art.request || null);
      if (art.request) {
        els.ticker.value = art.request.ticker || "";
        els.question.value = art.request.question || "";
      }
      if (art.report_md) {
        els.reportMd.textContent = art.report_md;
      }
      await renderTickerSummary(data.ticker);
    }
  } catch (e) {
    alert("과거 실행 불러오기 실패: " + e.message);
  }
}

// ---------- Watchlist ----------
async function renderWatchlist() {
  if (!els.watchlistList) return;
  try {
    const res = await fetch(API.watchlist);
    if (!res.ok) return;
    const data = await res.json();
    const items = data.items || [];

    if (els.watchlistSchedStatus) {
      const sched = data.scheduler || {};
      const running = sched.running ? "on" : "off";
      els.watchlistSchedStatus.textContent = `sched · ${running} · ${sched.runs_triggered ?? 0} runs`;
      els.watchlistSchedStatus.classList.toggle("on", !!sched.running);
    }

    if (items.length === 0) {
      els.watchlistList.innerHTML = `<li class="watchlist-empty">저장된 Watchlist 항목이 없습니다.</li>`;
      return;
    }

    els.watchlistList.innerHTML = items
      .map((it) => {
        const last = it.last_run_at ? timeAgo(it.last_run_at) : "—";
        const status = it.last_run_status
          ? `<span class="status-badge ${statusClass(it.last_run_status)}">${it.last_run_status.toUpperCase()}</span>`
          : `<span class="status-badge neutral">NEW</span>`;
        const interval = it.interval_hours
          ? `<span class="wl-interval">every ${it.interval_hours}h</span>`
          : `<span class="wl-interval muted">manual</span>`;
        const enabled = it.enabled ? "" : `<span class="wl-paused">paused</span>`;
        const err = it.last_run_error
          ? `<div class="wl-error" title="${escapeHtml(it.last_run_error)}">${escapeHtml(it.last_run_error.slice(0, 80))}</div>`
          : "";
        return `
          <li class="watchlist-item" data-id="${escapeHtml(it.id)}">
            <div class="wl-top">
              <div class="wl-ticker">${escapeHtml(it.ticker)}</div>
              ${status}
              ${enabled}
            </div>
            <div class="wl-question" title="${escapeHtml(it.question)}">${escapeHtml(it.question.length > 80 ? it.question.slice(0, 80) + "…" : it.question)}</div>
            <div class="wl-meta">
              ${interval}
              <span class="wl-last">last: ${last}</span>
              <span class="wl-count">· ${it.run_count || 0} runs</span>
            </div>
            ${err}
            <div class="wl-actions">
              <button type="button" class="linkish wl-run" data-id="${escapeHtml(it.id)}" title="지금 실행">run</button>
              <button type="button" class="linkish wl-load" data-id="${escapeHtml(it.id)}" title="폼에 불러오기">load</button>
              <button type="button" class="linkish wl-toggle" data-id="${escapeHtml(it.id)}" data-enabled="${it.enabled}" title="일시정지/재개">${it.enabled ? "pause" : "resume"}</button>
              <button type="button" class="linkish danger wl-delete" data-id="${escapeHtml(it.id)}" title="삭제">del</button>
            </div>
          </li>`;
      })
      .join("");

    state.watchlistItems = items;
    wireWatchlistActions();
  } catch (err) {
    console.warn("watchlist load failed", err);
  }
}

function wireWatchlistActions() {
  els.watchlistList.querySelectorAll(".wl-run").forEach((btn) => {
    btn.addEventListener("click", () => watchlistRunNow(btn.dataset.id));
  });
  els.watchlistList.querySelectorAll(".wl-load").forEach((btn) => {
    btn.addEventListener("click", () => watchlistLoadToForm(btn.dataset.id));
  });
  els.watchlistList.querySelectorAll(".wl-toggle").forEach((btn) => {
    btn.addEventListener("click", () => watchlistToggle(btn.dataset.id, btn.dataset.enabled !== "true"));
  });
  els.watchlistList.querySelectorAll(".wl-delete").forEach((btn) => {
    btn.addEventListener("click", () => watchlistDelete(btn.dataset.id));
  });
}

async function watchlistAddFromForm() {
  const payload = readForm();
  if (!payload.ticker || !payload.question) {
    alert("Ticker / Question 을 먼저 채워주세요.");
    return;
  }
  const intervalStr = prompt(
    "자동 실행 주기 (시간 단위, 비워두면 수동 실행만):",
    ""
  );
  let interval_hours = null;
  if (intervalStr && intervalStr.trim()) {
    const parsed = parseFloat(intervalStr);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      alert("잘못된 주기입니다. 양수 시간 값을 입력하세요.");
      return;
    }
    interval_hours = parsed;
  }
  try {
    const res = await fetch(API.watchlist, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: payload.ticker,
        question: payload.question,
        sources: payload.sources,
        lookback_days: payload.lookback_days,
        top_k: payload.top_k,
        model: payload.model,
        interval_hours,
        enabled: true,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    await renderWatchlist();
  } catch (err) {
    alert(`Watchlist 저장 실패: ${err.message || err}`);
  }
}

async function watchlistRunNow(id) {
  const btn = els.watchlistList.querySelector(`.wl-run[data-id="${id}"]`);
  if (btn) { btn.disabled = true; btn.textContent = "running…"; }
  try {
    const res = await fetch(`${API.watchlist}/${encodeURIComponent(id)}/run`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    await renderWatchlist();
    await renderHistory();
    if (data.response) {
      renderResponse(data.response, null, {
        ticker: data.response.ticker,
        question: data.response.question,
      });
    }
  } catch (err) {
    alert(`실행 실패: ${err.message || err}`);
    if (btn) { btn.disabled = false; btn.textContent = "run"; }
  }
}

function watchlistLoadToForm(id) {
  const item = (state.watchlistItems || []).find((x) => x.id === id);
  if (!item) return;
  els.ticker.value = item.ticker;
  els.question.value = item.question;
  els.lookback.value = String(item.lookback_days);
  els.topk.value = String(item.top_k);
  els.model.value = item.model;
  els.sourceInputs().forEach((i) => {
    if (i.disabled) return;
    i.checked = (item.sources || []).includes(i.value);
  });
  updateRangeLabels();
  persistForm();
  els.ticker.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function watchlistToggle(id, enable) {
  try {
    const res = await fetch(`${API.watchlist}/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !!enable,
        // Required fields must be echoed back for the request schema; store-side
        // merge preserves everything else.
        ticker: (state.watchlistItems.find(x => x.id === id) || {}).ticker,
        question: (state.watchlistItems.find(x => x.id === id) || {}).question,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    await renderWatchlist();
  } catch (err) {
    alert(`토글 실패: ${err.message || err}`);
  }
}

async function watchlistDelete(id) {
  const item = (state.watchlistItems || []).find((x) => x.id === id);
  if (!item) return;
  if (!confirm(`'${item.ticker}' Watchlist 항목을 삭제하시겠습니까?`)) return;
  try {
    const res = await fetch(`${API.watchlist}/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await renderWatchlist();
  } catch (err) {
    alert(`삭제 실패: ${err.message || err}`);
  }
}

function timeAgo(iso) {
  try {
    const ts = new Date(iso).getTime();
    if (!ts) return "—";
    const diff = (Date.now() - ts) / 1000;
    if (diff < 60) return `${Math.round(diff)}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  } catch { return "—"; }
}

async function renderTickerSummary(ticker) {
  if (!ticker) { els.tickerSummary?.classList.add("hidden"); return; }
  if (!els.tickerSummary) return;
  try {
    const res = await fetch(API.runSummary(ticker));
    if (!res.ok) { els.tickerSummary.classList.add("hidden"); return; }
    const data = await res.json();
    const points = data.points || [];
    if (!points.length) { els.tickerSummary.classList.add("hidden"); return; }
    els.tickerSummary.classList.remove("hidden");
    renderSparkline(points);
  } catch {
    els.tickerSummary?.classList.add("hidden");
  }
}

function renderSparkline(points) {
  if (!els.sparkline) return;
  const w = 240, h = 60, pad = 6;
  const vals = points.map(p => Number(p.confidence || 0));
  const n = vals.length;
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", h);

  if (n >= 2) {
    const maxV = Math.max(1, ...vals), minV = 0;
    const step = (w - pad * 2) / (n - 1);
    const path = vals.map((v, i) => {
      const x = pad + i * step;
      const y = h - pad - ((v - minV) / (maxV - minV || 1)) * (h - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    const p = document.createElementNS(svgNS, "path");
    p.setAttribute("d", path);
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", "#5ec2a4");
    p.setAttribute("stroke-width", "1.8");
    p.setAttribute("stroke-linecap", "round");
    p.setAttribute("stroke-linejoin", "round");
    svg.appendChild(p);
  }

  points.forEach((pt, i) => {
    const x = pad + (n > 1 ? i * ((w - pad * 2) / (n - 1)) : (w / 2));
    const y = h - pad - (Number(pt.confidence || 0)) * (h - pad * 2);
    const c = document.createElementNS(svgNS, "circle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y.toFixed(1));
    c.setAttribute("r", "2.5");
    const tone = (pt.sentiment || "").toLowerCase();
    c.setAttribute("fill", tone.includes("pos") ? "#4ade80" : tone.includes("neg") ? "#f87171" : "#9aa3b2");
    svg.appendChild(c);
  });

  els.sparkline.innerHTML = "";
  els.sparkline.appendChild(svg);

  if (els.sparklineLabel) {
    const last = points[points.length - 1];
    els.sparklineLabel.textContent = `최근 ${points.length}회 · 최종 ${last.status}/${last.sentiment}`;
  }
}

// ---------- Stage animation ----------
function progressNode(stage) {
  if (!stage || !els.progressStages) return null;
  return els.progressStages.querySelector(`[data-stage="${stage}"]`);
}

function startStageAnimation() {
  state.stageIndex = 0;
  if (!els.progressStages) return;
  STAGES.forEach((s) => {
    const node = progressNode(s);
    if (!node) return;
    node.classList.remove("active", "done");
  });
  const advance = () => {
    if (state.stageIndex < STAGES.length) {
      STAGES.forEach((s, i) => {
        const node = progressNode(s);
        if (!node) return;
        if (i < state.stageIndex) { node.classList.add("done"); node.classList.remove("active"); }
        else if (i === state.stageIndex) { node.classList.add("active"); node.classList.remove("done"); }
      });
      state.stageIndex++;
    }
  };
  advance();
  // simulated stage progression: Collect=3s, Ingest=2s, Retrieve=2s, Infer=20s+, Analyze=2s, Report=1s
  const delays = [3500, 2200, 2000, 20000, 2500, 1500];
  const tick = () => {
    if (state.stageIndex >= STAGES.length) return;
    state.stageTimer = setTimeout(() => {
      advance();
      tick();
    }, delays[state.stageIndex - 1] || 2000);
  };
  tick();
}

function finishStageAnimation() {
  clearTimeout(state.stageTimer);
  if (!els.progressStages) return;
  STAGES.forEach((s) => {
    const node = progressNode(s);
    if (!node) return;
    node.classList.remove("active");
    node.classList.add("done");
  });
}

function startTimer() {
  state.startedAt = Date.now();
  const tick = () => {
    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const ss = String(elapsed % 60).padStart(2, "0");
    els.loadingTimer.textContent = `${mm}:${ss}`;
  };
  tick();
  state.pendingTimer = setInterval(tick, 1000);
}
function stopTimer() {
  clearInterval(state.pendingTimer);
}

function setExportAvailability(enabled) {
  const controls = [
    els.downloadMdBtn,
    els.downloadJsonBtn,
    els.openHtmlBtn,
    document.getElementById("exportToggleBtn"),
  ].filter(Boolean);
  controls.forEach((node) => {
    node.disabled = !enabled;
    node.classList.toggle("disabled", !enabled);
  });
}

async function fetchLatestCollectionArtifact() {
  try {
    const latest = await fetch(API.latest);
    if (!latest.ok) return null;
    const blob = await latest.json();
    return blob.collection || null;
  } catch {
    return null;
  }
}

async function runStreamAnalysis(url, payload, renderRequest) {
  let finalData = null;
  let streamError = null;
  state.activeRequest = renderRequest;
  state.streamHasPartial = false;
  setExportAvailability(false);

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json())?.detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }

  for await (const frame of iterSseFrames(res.body)) {
    if (!frame.event) continue;
    handleStreamEvent(frame.event, frame.data);
    if (frame.event === "result") {
      finalData = frame.data;
    } else if (frame.event === "pipeline_failed") {
      streamError = frame.data?.reason || "Pipeline failed";
    }
  }

  if (streamError && !finalData) {
    throw new Error(streamError);
  }
  if (!finalData) {
    throw new Error("스트림이 결과 이벤트 없이 종료되었습니다.");
  }

  if (finalData.mode === "multi_ticker") {
    renderCompareResponse(finalData);
  } else {
    renderResponse(finalData, null, renderRequest);
    fetchLatestCollectionArtifact().then((collection) => {
      if (!collection || state.lastResponse !== finalData) return;
      state.lastCollection = collection;
      renderDiagnostics(renderRequest, collection);
    }).catch(() => {});
  }
}

// ---------- Run analysis ----------
async function runAnalysis(e) {
  e.preventDefault();
  const payload = readForm();
  setFormNotice("");

  const requiresTicker = payload.compare || payload.mode_hint === "ticker";
  if (requiresTicker && !payload.ticker) {
    els.ticker.focus();
    setFormNotice("종목 모드는 ticker가 필요합니다. ticker 없이 질문하려면 자동 또는 주제 모드를 선택하세요.", "warning");
    return;
  }
  if (!payload.question) {
    els.question.focus();
    setFormNotice("질문을 입력해야 분석을 실행할 수 있습니다.", "warning");
    return;
  }
  if (payload.sources.length === 0) {
    setFormNotice("최소 한 개의 소스를 선택해야 합니다.", "warning");
    return;
  }

  if (payload.compare) {
    if (payload.tickers.length < 2) {
      setFormNotice("Compare mode는 2개 이상의 ticker가 필요합니다. 쉼표 또는 공백으로 구분하세요.", "warning");
      els.ticker.focus();
      return;
    }
    persistForm();
    await runCompare(payload);
    return;
  }

  persistForm();
  setLoading(true, payload.ticker || "TOPIC");
  if (payload.extracted_ticker) {
    els.loadingSub.textContent = `질문에서 ${payload.extracted_ticker} 티커를 감지했습니다. Universal 라우터로 경로를 판별합니다.`;
  }
  try {
    await runStreamAnalysis(API.universalStream, payload, payload);
    renderHistory();
    if (payload.ticker && !payload.compare) renderTickerSummary(payload.ticker);
  } catch (err) {
    console.error(err);
    renderFailure(payload, err.message || String(err));
  } finally {
    state.activeRequest = null;
    setLoading(false);
  }
}

// ---------- Compare mode ----------
async function runCompare(payload) {
  // Compare mode owns the full-page state; wipe any prior single-run so the
  // post-compare setLoading(false) call doesn't flash the old result back in.
  state.lastResponse = null;
  state.lastCollection = null;
  state.lastRequest = null;
  setLoading(true, payload.tickers.join(", "));
  els.loadingSub.textContent = `${payload.tickers.length}개 티커 동시 분석 중…`;
  resetProgressStages();

  try {
    const body = {
      tickers: payload.tickers,
      question: payload.question,
      sources: payload.sources,
      lookback_days: payload.lookback_days,
      top_k: payload.top_k,
      model: payload.model,
      concurrency: 2,
    };
    const res = await fetch(API.compare, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data?.detail || `HTTP ${res.status}`);
    }
    // Hide loading/empty, then reveal the compare view without touching
    // resultView visibility.
    els.loadingState.classList.add("hidden");
    els.emptyState.classList.add("hidden");
    els.runBtn.disabled = false;
    els.runBtn.classList.remove("loading");
    stopTimer();
    finishStageAnimation();
    renderCompareResponse(data);
    renderHistory();
  } catch (err) {
    console.error(err);
    renderFailure({ ticker: payload.tickers.join(","), question: payload.question }, err.message || String(err));
    setLoading(false);
  }
}

function renderCompareResponse(data) {
  state.lastResponse = null;
  state.lastCollection = null;
  state.lastRequest = null;
  setExportAvailability(false);

  els.emptyState.classList.add("hidden");
  els.loadingState.classList.add("hidden");
  els.resultView.classList.add("hidden");
  els.compareView.classList.remove("hidden");

  const results = data.results || {};
  const tickers = data.tickers || Object.keys(results);

  els.compareMeta.textContent = `${tickers.length} tickers · ${data.elapsed_s ?? "?"}s · concurrency=${data.concurrency ?? 1}`;

  // Side-by-side metric table
  const rows = [
    { label: "Status", cell: (r) => `<span class="status-badge ${statusClass(r.status)}">${(r.status || "").toUpperCase()}</span>` },
    { label: "Sentiment", cell: (r) => r.sentiment || "—" },
    { label: "Confidence", cell: (r) => (r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—") },
    { label: "Bull / Bear", cell: (r) => `${(r.bull_points || []).length} / ${(r.bear_points || []).length}` },
    { label: "Citations", cell: (r) => (r.citations || []).length },
    { label: "Latency", cell: (r) => (r.execution_meta?.pipeline_latency_s != null ? `${r.execution_meta.pipeline_latency_s}s` : "—") },
    { label: "Producing model", cell: (r) => r.execution_meta?.producing_model || "—" },
  ];
  const header = `<thead><tr><th></th>${tickers.map((t) => `<th>${escapeHtml(t)}</th>`).join("")}</tr></thead>`;
  const bodyHtml = rows
    .map((row) => {
      const cells = tickers
        .map((t) => {
          const r = results[t] || {};
          return `<td>${row.cell(r)}</td>`;
        })
        .join("");
      return `<tr><th>${row.label}</th>${cells}</tr>`;
    })
    .join("");
  els.compareTable.innerHTML = `<table class="compare-grid">${header}<tbody>${bodyHtml}</tbody></table>`;

  // Summaries — one card per ticker
  const cards = tickers.map((t) => {
    const r = results[t] || {};
    const err = r.error_metadata ? `<div class="compare-error">${escapeHtml(r.error_metadata)}</div>` : "";
    const bull = (r.bull_points || []).slice(0, 3).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    const bear = (r.bear_points || []).slice(0, 3).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
    return `
      <div class="compare-card ${statusClass(r.status)}">
        <div class="compare-card-head"><h4>${escapeHtml(t)}</h4><span class="status-badge ${statusClass(r.status)}">${(r.status || "").toUpperCase()}</span></div>
        ${err}
        <p class="compare-summary">${escapeHtml(r.summary || "—")}</p>
        <div class="compare-sides">
          <div class="compare-side bull"><h5>Bull</h5><ul>${bull || "<li class='muted'>—</li>"}</ul></div>
          <div class="compare-side bear"><h5>Bear</h5><ul>${bear || "<li class='muted'>—</li>"}</ul></div>
        </div>
        <p class="compare-conclusion">${escapeHtml(r.conclusion || "")}</p>
      </div>`;
  });
  els.compareSummaries.innerHTML = cards.join("");
}

function updateCompareModeUI() {
  const on = !!(els.compareMode && els.compareMode.checked);
  const mode = Array.from(els.researchModeInputs()).find((i) => i.checked)?.value || "auto";
  if (!els.ticker) return;
  const placeholder = on
    ? "AAPL, MSFT, NVDA"
    : mode === "topic"
      ? "선택: TLT, GLD, BTC-USD"
      : mode === "ticker"
        ? "필수: AAPL"
        : "선택: TLT, GLD, BTC-USD 또는 AAPL";
  els.ticker.placeholder = placeholder;
  if (els.tickerHint) {
    els.tickerHint.textContent = on
      ? "쉼표/공백으로 2-5개 티커 구분"
      : mode === "topic"
        ? "ticker 없이 질의 가능, ticker는 참고 힌트"
        : mode === "ticker"
          ? "종목 분석은 ticker 필수"
          : "ticker 선택 입력, 비워두면 주제/거시 질의";
  }
  // Swap chip behavior: in compare mode chips append with a comma rather than replace.
  els.ticker.dataset.mode = on ? "compare" : "single";
}

// ---------- SSE helpers ----------
async function* iterSseFrames(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const frame = parseSseFrame(raw);
        if (frame) yield frame;
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* ignore */ }
  }
}

function parseSseFrame(raw) {
  if (!raw || raw.startsWith(":")) return null;
  let event = "message";
  const dataLines = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(payload) };
  } catch {
    return { event, data: payload };
  }
}

function handleStreamEvent(event, data) {
  if (event === "stream_open") {
    state.streamStartedAt = Date.now();
    state.streamHasPartial = false;
    resetProgressStages();
    setExportAvailability(false);
    return;
  }
  if (event === "stage_started") {
    markStageActive(data?.stage);
    const substatus = describeStageStart(data);
    if (substatus) els.loadingSub.textContent = substatus;
    return;
  }
  if (event === "stage_completed") {
    markStageDone(data?.stage, data);
    const substatus = describeStageDone(data);
    if (substatus) els.loadingSub.textContent = substatus;
    return;
  }
  if (event === "pipeline_completed") {
    finishStageAnimation();
    els.loadingSub.textContent = `최종 정리 완료 · ${data?.elapsed_s ?? "?"}s`;
    return;
  }
  if (event === "partial_result") {
    state.streamHasPartial = true;
    const payload = data?.payload || data;
    if (payload && typeof payload === "object") {
      renderResponse(payload, state.lastCollection, state.activeRequest || state.lastRequest);
    }
    els.loadingSub.textContent = "초기 판단 생성 완료 · 심화 보강 중";
    return;
  }
  if (event === "pipeline_failed") {
    els.loadingSub.textContent = `실패: ${data?.reason || "unknown"}`;
    return;
  }
}

function resetProgressStages() {
  if (!els.progressStages) return;
  STAGES.forEach((s) => {
    const node = progressNode(s);
    if (node) node.classList.remove("active", "done");
  });
}

function markStageActive(stage) {
  const node = progressNode(stage);
  if (!node) return;
  els.progressStages.querySelectorAll("[data-stage].active").forEach((n) => n.classList.remove("active"));
  node.classList.add("active");
  node.classList.remove("done");
}

function markStageDone(stage, data) {
  const node = progressNode(stage);
  if (!node) return;
  node.classList.remove("active");
  node.classList.add("done");
  if (data?.status && data.status !== "ok") {
    node.classList.add("warn");
  }
}

function describeStageStart(data) {
  const s = data?.stage;
  if (!s) return "";
  const map = {
    collect: "관련 문서 수집 중",
    ingest: `벡터 DB 적재 중 (${data.documents ?? 0} docs)`,
    retrieve: `컨텍스트 검색 중 (top_k=${data.top_k ?? "?"})`,
    infer: `LLM 추론 중 (${data.chunks ?? 0} chunks)`,
    analyze: "분석 결과 정리 중",
    report: "리포트 생성 중",
    output: "산출물 저장 중",
  };
  return map[s] || `${s} 진행 중`;
}

function describeStageDone(data) {
  const s = data?.stage;
  if (!s) return "";
  const dur = data.duration_s != null ? `${data.duration_s}s` : "";
  const extras = [];
  if (s === "collect") {
    if (data.cache_hit) extras.push(`cache ${formatAge(data.cache_age_s)}`);
    if (data.documents != null) extras.push(`${data.documents} docs`);
    if ((data.degraded_sources || []).length) extras.push(`degraded: ${data.degraded_sources.join(", ")}`);
  } else if (s === "retrieve" && data.chunks != null) {
    extras.push(`${data.chunks} chunks`);
  } else if (s === "analyze" && data.sentiment) {
    extras.push(`${data.sentiment}${data.confidence != null ? ` ${Math.round(data.confidence * 100)}%` : ""}`);
  }
  const extraStr = extras.length ? ` · ${extras.join(" · ")}` : "";
  return `${s} 완료${dur ? ` · ${dur}` : ""}${extraStr}`;
}

function setLoading(isLoading, ticker) {
  els.emptyState.classList.toggle("hidden", true);
  els.loadingState.classList.toggle("hidden", !isLoading);
  els.resultView.classList.toggle("hidden", isLoading || !state.lastResponse);
  if (els.compareView) els.compareView.classList.toggle("hidden", isLoading || state.lastResponse !== null);
  els.runBtn.disabled = isLoading;
  els.runBtn.classList.toggle("loading", isLoading);
  if (isLoading) {
    setExportAvailability(false);
    els.loadingTicker.textContent = ticker || "분석 중";
    els.loadingSub.textContent = "스트림 연결 중";
    startTimer();
    resetProgressStages();
  } else {
    stopTimer();
    finishStageAnimation();
  }
}

// ---------- Render ----------
function cleanLine(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeProseLines(value) {
  return String(value || "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim());
}

function isProseHeading(line) {
  return /^(핵심 분석|핵심 지표|Synthesis|Decision Edge|결론|요약|상방 동인|하방 리스크|관련 종목|관련 자산|불확실성|투자 판단|시장 가격|시나리오 분석|실행 전략)$/i.test(line)
    || /^\(\d+\)\s+/.test(line)
    || /^#{1,6}\s+/.test(line);
}

function compactProseLines(lines) {
  const out = [];
  (Array.isArray(lines) ? lines : []).forEach((line) => {
    const text = String(line ?? "");
    if (!text.trim()) {
      if (out.length && out[out.length - 1] !== "") out.push("");
      return;
    }
    out.push(text.trim());
  });
  while (out.length && out[0] === "") out.shift();
  while (out.length && out[out.length - 1] === "") out.pop();
  return out;
}

function joinProseLines(lines) {
  return compactProseLines(lines).join("\n");
}

function renderProse(container, value, fallback = "—") {
  if (!container) return;
  const lines = compactProseLines(normalizeProseLines(value));
  container.innerHTML = "";
  if (!lines.length) {
    const p = document.createElement("p");
    p.className = "prose-paragraph muted";
    p.textContent = fallback;
    container.appendChild(p);
    return;
  }

  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = document.createElement("p");
    p.className = "prose-paragraph";
    p.textContent = paragraph.join(" ");
    container.appendChild(p);
    paragraph = [];
  };

  const closeList = () => {
    list = null;
  };

  lines.forEach((line) => {
    if (!line) {
      flushParagraph();
      closeList();
      return;
    }
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      if (!list) {
        list = document.createElement("ul");
        list.className = "prose-list";
        container.appendChild(list);
      }
      const li = document.createElement("li");
      li.textContent = bullet[1].trim();
      list.appendChild(li);
      return;
    }
    closeList();
    if (isProseHeading(line)) {
      flushParagraph();
      const heading = document.createElement("h4");
      heading.className = "prose-heading";
      heading.textContent = line.replace(/^#{1,6}\s+/, "");
      container.appendChild(heading);
      return;
    }
    paragraph.push(line);
  });
  flushParagraph();
}

function dedupeKey(value) {
  return cleanLine(value).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

function uniqueTextItems(items) {
  const out = [];
  const seen = new Set();
  (Array.isArray(items) ? items : []).forEach((item) => {
    const text = cleanLine(item);
    if (!text) return;
    const key = dedupeKey(text);
    if (key && seen.has(key)) return;
    if (key) seen.add(key);
    out.push(text);
  });
  return out;
}

function dedupeReportLines(lines) {
  const keepRepeat = /^(핵심 분석|Synthesis|Decision Edge|결론|상방 동인|하방 리스크|관련 종목|관련 자산|불확실성|\(\d+\)|요약|상승 촉매|하락 촉매|투자 판단)/i;
  const seen = new Set();
  return (Array.isArray(lines) ? lines : []).filter((line) => {
    const text = cleanLine(line);
    if (!text) return true;
    if (keepRepeat.test(text) || text === "") return true;
    const key = dedupeKey(text.replace(/^-+\s*/, "").replace(/^결론:\s*/, ""));
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function listLines(items, emptyText = "식별된 항목 없음") {
  const values = uniqueTextItems((Array.isArray(items) ? items : [])
    .map((item) => cleanLine(typeof item === "string" ? item : item?.text || item))
    .filter(Boolean));
  return values.length ? values.map((item) => `- ${item}`) : [`- ${emptyText}`];
}

function formatMetricLine(metric) {
  if (!metric) return "";
  const name = cleanLine(metric.name);
  const value = cleanLine(metric.value);
  if (!name || !value) return "";
  const context = cleanLine(metric.context);
  const asOf = cleanLine(metric.as_of || metric.asOf);
  const unit = cleanLine(metric.unit);
  const source = cleanLine(metric.source);
  const asOfText = asOf || "기준일 미확인";
  const sourceText = source ? ` · 출처: ${source}` : "";
  return `${name}: ${value}${unit ? ` ${unit}` : ""} [기준일: ${asOfText}${sourceText}]${context ? ` (${context})` : ""}`;
}

function metricLines(metrics) {
  return listLines(
    (Array.isArray(metrics) ? metrics : []).map(formatMetricLine).filter(Boolean),
    "정량 지표가 추출되지 않았습니다."
  );
}

function compactMetricLine(metric) {
  const name = cleanLine(metric?.name);
  const value = cleanLine(metric?.value);
  if (!name || !value) return "";
  const unit = cleanLine(metric?.unit);
  const asOf = cleanLine(metric?.as_of || metric?.asOf) || "기준일 미확인";
  const source = cleanLine(metric?.source);
  return `${name} ${value}${unit ? ` ${unit}` : ""} · ${asOf}${source ? ` · ${source}` : ""}`;
}

function buildTopicHeadlineSummary(data) {
  const risks = (data.key_risks || []).map((x) => cleanLine(x.text || x)).filter(Boolean).slice(0, 3);
  const drivers = (data.key_drivers || []).map((x) => cleanLine(x.text || x)).filter(Boolean).slice(0, 2);
  const scenarioCount = Array.isArray(data.scenario_analysis) ? data.scenario_analysis.length : 0;
  const lines = [];
  if (data.executive_summary || data.summary) lines.push(cleanLine(data.executive_summary || data.summary));
  if (risks.length) lines.push(`핵심 리스크: ${risks.join(" / ")}`);
  if (drivers.length) lines.push(`확인할 상방 동인: ${drivers.join(" / ")}`);
  if (scenarioCount) lines.push(`시나리오 ${scenarioCount}개와 실행 전략 ${(data.execution_strategy || []).length}개를 기준으로 의사결정을 분해했습니다.`);
  return uniqueTextItems(lines).join("\n");
}

function buildTopicDecisionMemo(data, ...sections) {
  const lines = [];
  sections.filter(Boolean).forEach((section, index) => {
    if (index > 0) lines.push("");
    lines.push(section);
  });
  return joinProseLines(dedupeReportLines(lines));
}

function renderMetricTable(metrics) {
  if (!els.metricsTable) return;
  const rows = Array.isArray(metrics) ? metrics.filter((m) => m && cleanLine(m.name) && cleanLine(m.value)) : [];
  els.metricsTable.innerHTML = "";
  if (!rows.length) {
    els.metricsTable.innerHTML = `<div class="metric-empty">정량 지표가 추출되지 않았습니다.</div>`;
    return;
  }
  const evidenceIndex = buildEvidenceIndex(state.evidenceRaw);
  const table = document.createElement("table");
  table.className = "metric-table";
  table.innerHTML = `
    <thead><tr><th>지표</th><th>값</th><th>단위</th><th>기준일</th><th>출처</th><th>상태</th><th>맥락</th><th>근거</th></tr></thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector("tbody");
  rows.forEach((metric) => {
    const tr = document.createElement("tr");
    const docIds = Array.isArray(metric.evidence_doc_ids) ? metric.evidence_doc_ids : [];
    const evidenceTd = document.createElement("td");
    evidenceTd.className = "metric-evidence";
    if (docIds.length) {
      docIds.forEach((docId) => {
        const item = evidenceIndex.get(String(docId));
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "evidence-chip metric-chip";
        chip.textContent = item
          ? `${truncateLabel(docId, 10)} · ${item.date || "unknown"}`
          : `doc ${truncateLabel(docId, 10)}`;
        chip.title = item ? `${item.source || "doc"} · ${item.date || "unknown"}\n${item.title || docId}` : `doc_id: ${docId}`;
        chip.addEventListener("click", () => jumpToEvidence(docId));
        evidenceTd.appendChild(chip);
      });
    } else {
      evidenceTd.textContent = "근거 링크 없음";
      evidenceTd.className = "metric-evidence muted";
    }
    [
      metric.name,
      metric.value,
      metric.unit || "",
      metric.as_of || "unknown",
      metric.source || "",
      [metric.freshness_status || "unknown", metric.grounding_status || ""].filter(Boolean).join(" / "),
      metric.context || "",
    ].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = cleanLine(value) || "—";
      tr.appendChild(td);
    });
    tr.appendChild(evidenceTd);
    tbody.appendChild(tr);
  });
  els.metricsTable.appendChild(table);
}

function normalizeTextItem(item, fallback = "") {
  if (typeof item === "string") return cleanLine(item);
  if (!item || typeof item !== "object") return fallback;
  return cleanLine(item.text || item.title || item.scenario || item.strategy || item.conclusion || item.expected_outcome || fallback);
}

function renderDocBadges(container, docIds) {
  const ids = Array.isArray(docIds) ? docIds.filter(Boolean) : [];
  if (!ids.length) {
    const note = document.createElement("span");
    note.className = "evidence-note";
    note.textContent = "근거 링크 없음";
    container.appendChild(note);
    return;
  }
  const evidenceIndex = buildEvidenceIndex(state.evidenceRaw);
  ids.forEach((docId) => {
    const item = evidenceIndex.get(String(docId));
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "evidence-chip metric-chip";
    chip.textContent = item
      ? `${truncateLabel(docId, 10)} · ${item.date || "unknown"}`
      : `doc ${truncateLabel(docId, 10)}`;
    chip.title = item ? `${item.source || "doc"} · ${item.date || "unknown"}\n${item.title || docId}` : `doc_id: ${docId}`;
    chip.addEventListener("click", () => jumpToEvidence(docId));
    container.appendChild(chip);
  });
}

function getQuantMetrics(data, snapshot = null) {
  const snap = snapshot || data?.execution_meta?.extras?.quant_snapshot || {};
  const snapMetrics = Array.isArray(snap.metrics) ? snap.metrics : [];
  const keyMetrics = Array.isArray(data?.key_metrics) ? data.key_metrics : [];
  return snapMetrics.length ? snapMetrics : keyMetrics;
}

function metricSearchText(metric) {
  return [
    metric?.name,
    metric?.context,
    metric?.source,
    metric?.unit,
  ].filter(Boolean).join(" ").toLowerCase();
}

function findMetric(metrics, needles) {
  const terms = Array.isArray(needles) ? needles : [needles];
  const lowered = terms.map((term) => String(term || "").toLowerCase()).filter(Boolean);
  return (metrics || []).find((metric) => lowered.some((term) => metricSearchText(metric).includes(term))) || null;
}

function parseMetricNumber(metric) {
  const value = metric?.value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const match = String(value ?? "").replace(/,/g, "").match(/[+-]?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function formatMetricValue(metric) {
  if (!metric) return "—";
  const raw = cleanLine(metric.value);
  const unit = cleanLine(metric.unit || "");
  if (!raw) return "—";
  if (unit === "%" && !String(raw).includes("%")) return `${raw}%`;
  if (unit && unit !== "price" && unit !== "index" && !String(raw).includes(unit)) return `${raw} ${unit}`;
  return raw;
}

function metricDocIds(metric) {
  return Array.isArray(metric?.evidence_doc_ids) ? metric.evidence_doc_ids.filter(Boolean) : [];
}

function cleanTextArray(value) {
  if (Array.isArray(value)) return value.map((item) => cleanLine(item)).filter(Boolean);
  const single = cleanLine(value);
  return single ? [single] : [];
}

function collectMetricDocIds(metrics, patterns, fallback = []) {
  const ids = [];
  (patterns || []).forEach((pattern) => {
    ids.push(...metricDocIds(findMetric(metrics, pattern)));
  });
  if (!ids.length && Array.isArray(fallback)) ids.push(...fallback.filter(Boolean));
  return Array.from(new Set(ids.map(String))).slice(0, 4);
}

function buildQuantRegime(metrics, data) {
  const extras = data?.execution_meta?.extras || {};
  const snapshot = extras.quant_snapshot || {};
  const snapshotRegime = snapshot.regime || {};
  const latest = findMetric(metrics, ["최신 종가", "latest close"]);
  const momentum1m = findMetric(metrics, ["1개월 가격 모멘텀", "1m momentum"]);
  const momentum3m = findMetric(metrics, ["3개월 가격 모멘텀", "3m momentum"]);
  const sma20 = findMetric(metrics, ["sma20"]);
  const sma50 = findMetric(metrics, ["sma50"]);
  const sma200 = findMetric(metrics, ["sma200"]);
  const rsi = findMetric(metrics, ["rsi"]);
  const macd = findMetric(metrics, ["macd"]);
  const volatility = findMetric(metrics, ["실현 변동성", "realized volatility"]);
  const volume = findMetric(metrics, ["평균 대비 거래량", "volume"]);

  const m1 = parseMetricNumber(momentum1m);
  const m3 = parseMetricNumber(momentum3m);
  const d20 = parseMetricNumber(sma20);
  const d50 = parseMetricNumber(sma50);
  const d200 = parseMetricNumber(sma200);
  const rsiValue = parseMetricNumber(rsi);
  const macdValue = parseMetricNumber(macd);
  const volValue = parseMetricNumber(volatility);
  const volRatio = parseMetricNumber(volume);

  let trendTitle = "가격 레짐 판단 보류";
  if (m1 !== null || d20 !== null || d50 !== null || d200 !== null) {
    const shortPositive = (m1 ?? 0) > 0 && (d20 ?? 0) > 0 && (d50 ?? 0) > 0;
    const longConfirmed = (d200 ?? 0) > 0;
    const mediumWeak = (m3 ?? 0) < 0 || (d200 ?? 0) < 0;
    if (shortPositive && longConfirmed) trendTitle = "상승 추세 우위";
    else if (shortPositive && mediumWeak) trendTitle = "단기 반등 우위, 장기 추세 검증 필요";
    else if ((m1 ?? 0) < 0 && (d20 ?? 0) < 0) trendTitle = "하락 모멘텀 우위";
    else trendTitle = "혼조 레짐";
  }

  let momentumTitle = "모멘텀 신호 제한";
  if (rsiValue !== null || macdValue !== null) {
    if ((rsiValue ?? 50) >= 70 && (macdValue ?? 0) > 0) momentumTitle = "상승 모멘텀은 강하지만 과열 리스크 존재";
    else if ((rsiValue ?? 50) <= 30) momentumTitle = "침체권 반등 후보";
    else if ((macdValue ?? 0) > 0) momentumTitle = "모멘텀 개선 구간";
    else if ((macdValue ?? 0) < 0) momentumTitle = "모멘텀 둔화 구간";
  }

  let riskTitle = "리스크 신호 추가 확인 필요";
  if ((rsiValue ?? 0) >= 70 || (volValue ?? 0) >= 35 || (d200 ?? 0) < 0) {
    riskTitle = "추격 매수보다 확인 매수가 유리한 리스크 구조";
  } else if ((m1 ?? 0) > 0 && (macdValue ?? 0) > 0) {
    riskTitle = "상방 추세 유지 가능성이 있으나 이벤트 확인 필요";
  }

  const evidenceFallback = Array.isArray(data?.cited_doc_ids) ? data.cited_doc_ids : [];
  const importantMetrics = [latest, momentum1m, momentum3m, sma20, sma50, sma200, rsi, macd, volatility, volume].filter(Boolean);
  const signalLine = importantMetrics.slice(0, 4).map((metric) => `${cleanLine(metric.name)} ${formatMetricValue(metric)}`).join(" · ");
  const confirmingLine = cleanTextArray(snapshotRegime.confirming_signals).slice(0, 4).join(" · ");
  const invalidationLine = cleanTextArray(snapshotRegime.invalidation_signals).slice(0, 4).join(" · ");
  const snapshotFreshness = snapshot.freshness_status || snapshot.data_freshness || "";
  const biasBody = [
    signalLine ? `핵심 지표: ${signalLine}` : "",
    confirmingLine ? `확인 신호: ${confirmingLine}` : "",
    invalidationLine ? `무효화/주의 신호: ${invalidationLine}` : "",
    snapshotFreshness ? `신선도: ${snapshotFreshness}` : "",
  ].filter(Boolean).join(" ");

  return {
    cards: [
      {
        label: "Bias",
        title: cleanLine(snapshotRegime.decision_bias) || trendTitle,
        body: biasBody || "가격, 추세, 변동성 지표가 충분하지 않아 레짐을 보수적으로 해석해야 합니다.",
        docIds: collectMetricDocIds(metrics, [["1개월 가격 모멘텀"], ["sma20"], ["sma50"], ["sma200"]], evidenceFallback),
      },
      {
        label: "Momentum",
        title: momentumTitle,
        body: [
          rsi ? `RSI(14) ${formatMetricValue(rsi)}는 단기 과열/침체 여부를 판단하는 핵심 신호입니다.` : "",
          macd ? `MACD 히스토그램 ${formatMetricValue(macd)}는 추세 가속 또는 둔화를 확인하는 보조 신호입니다.` : "",
        ].filter(Boolean).join(" "),
        docIds: collectMetricDocIds(metrics, [["rsi"], ["macd"]], evidenceFallback),
      },
      {
        label: "Risk",
        title: riskTitle,
        body: [
          volatility ? `20일 실현 변동성 ${formatMetricValue(volatility)}를 기준으로 포지션 크기와 손절 폭을 조정해야 합니다.` : "",
          volume ? `거래량 신호 ${formatMetricValue(volume)}는 가격 움직임의 신뢰도를 검증하는 데 사용합니다.` : "",
          (d200 ?? 0) < 0 ? "SMA200 아래에 머무르면 장기 추세가 완전히 복원됐다고 보기 어렵습니다." : "",
        ].filter(Boolean).join(" ") || "현재 지표만으로는 리스크 강도를 단정하기 어렵습니다.",
        docIds: collectMetricDocIds(metrics, [["실현 변동성"], ["volume"], ["sma200"]], evidenceFallback),
      },
      {
        label: "Decision Read",
        title: data?.sentiment ? `${data.sentiment} · confidence ${data.confidence ?? "—"}` : "정량 판단",
        body: "정량 판단은 방향성보다 조건부 의사결정에 초점을 둡니다. 추세 지속은 모멘텀 유지와 거래량 확인이 필요하고, 과열 신호가 있으면 분할 진입과 손절 기준을 먼저 정해야 합니다.",
        docIds: collectMetricDocIds(metrics, [["최신 종가"], ["1개월 가격 모멘텀"], ["rsi"]], evidenceFallback),
      },
    ],
  };
}

function renderQuantRegime(data, metrics) {
  if (!metrics.length) return null;
  const regime = buildQuantRegime(metrics, data);
  const section = document.createElement("section");
  section.className = "quant-section quant-regime-section";
  section.innerHTML = `<h4>Quant Regime & Decision Read</h4>`;
  const grid = document.createElement("div");
  grid.className = "quant-regime-grid";
  regime.cards.forEach((item) => {
    const card = document.createElement("article");
    card.className = "quant-regime-card";
    card.innerHTML = `
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.body || "판단 근거가 제한적입니다.")}</p>
    `;
    const badges = document.createElement("div");
    badges.className = "evidence-chips";
    renderDocBadges(badges, item.docIds || []);
    card.appendChild(badges);
    grid.appendChild(card);
  });
  section.appendChild(grid);
  return section;
}

function deriveScenarioPackage(data) {
  const extras = data?.execution_meta?.extras || {};
  const snapshot = extras.quant_snapshot || {};
  const metrics = getQuantMetrics(data, snapshot);
  const ticker = data?.ticker || snapshot.target || "대상 자산";
  const evidenceFallback = Array.isArray(data?.cited_doc_ids) ? data.cited_doc_ids : [];
  const bull = Array.isArray(data?.bull_points) ? data.bull_points.map((x) => normalizeTextItem(x)).filter(Boolean) : [];
  const bear = Array.isArray(data?.bear_points) ? data.bear_points.map((x) => normalizeTextItem(x)).filter(Boolean) : [];
  const timeline = data?.catalyst_timeline || {};
  const catalysts = [
    ...cleanTextArray(timeline.near_term),
    ...cleanTextArray(timeline.mid_term),
    ...cleanTextArray(timeline.long_term),
  ];

  const momentum1m = findMetric(metrics, ["1개월 가격 모멘텀", "1m momentum"]);
  const momentum3m = findMetric(metrics, ["3개월 가격 모멘텀", "3m momentum"]);
  const sma20 = findMetric(metrics, ["sma20"]);
  const sma50 = findMetric(metrics, ["sma50"]);
  const sma200 = findMetric(metrics, ["sma200"]);
  const rsi = findMetric(metrics, ["rsi"]);
  const macd = findMetric(metrics, ["macd"]);
  const volatility = findMetric(metrics, ["실현 변동성", "realized volatility"]);
  const m1 = parseMetricNumber(momentum1m);
  const m3 = parseMetricNumber(momentum3m);
  const d20 = parseMetricNumber(sma20);
  const d50 = parseMetricNumber(sma50);
  const d200 = parseMetricNumber(sma200);
  const rsiValue = parseMetricNumber(rsi);
  const macdValue = parseMetricNumber(macd);

  const baseDocs = collectMetricDocIds(metrics, [["1개월 가격 모멘텀"], ["sma20"], ["sma50"], ["rsi"]], evidenceFallback);
  const bullDocs = collectMetricDocIds(metrics, [["macd"], ["sma200"], ["3개월 가격 모멘텀"]], evidenceFallback);
  const bearDocs = collectMetricDocIds(metrics, [["rsi"], ["실현 변동성"], ["sma20"], ["sma200"]], evidenceFallback);

  const trendRead = [
    momentum1m ? `1개월 모멘텀 ${formatMetricValue(momentum1m)}` : "",
    momentum3m ? `3개월 모멘텀 ${formatMetricValue(momentum3m)}` : "",
    sma20 ? `SMA20 괴리 ${formatMetricValue(sma20)}` : "",
    sma200 ? `SMA200 괴리 ${formatMetricValue(sma200)}` : "",
  ].filter(Boolean).join(", ");
  const momentumRead = [
    rsi ? `RSI ${formatMetricValue(rsi)}` : "",
    macd ? `MACD 히스토그램 ${formatMetricValue(macd)}` : "",
  ].filter(Boolean).join(", ");

  const scenarios = [
    {
      scenario: "Base: 상승 후 검증 구간",
      probability: "조건부 기본 시나리오",
      expected_outcome: trendRead
        ? `${ticker}는 ${trendRead} 기준으로 단기 가격 탄력은 확인되지만, 중기 추세와 장기 평균선 복원 여부가 다음 판단 변수입니다.`
        : `${ticker}는 가격/추세 데이터가 제한적이므로 수집 근거와 다음 실적 이벤트 확인이 필요합니다.`,
      asset_implication: "추세가 유지되면 완만한 상방은 열려 있지만, 과열 신호가 있으면 신규 진입 기대값은 낮아집니다.",
      decision_read: "분할 접근과 확인 매수 중심. 한 번에 추격하기보다 SMA20/50 지지와 거래량 동반 여부를 확인합니다.",
      evidence_doc_ids: baseDocs,
    },
    {
      scenario: "Bull: 모멘텀 재가속과 기대치 상향",
      probability: "상방 시나리오",
      expected_outcome: [
        momentumRead || "모멘텀 지표 개선",
        bull[0] || catalysts[0] || "실적/가이던스 또는 핵심 사업 지표 개선",
      ].filter(Boolean).join(" + "),
      asset_implication: (d200 ?? 0) < 0
        ? "SMA200 회복과 함께 중장기 추세 복원이 확인되면 멀티플 리레이팅 여지가 커집니다."
        : "이미 장기 추세가 우호적이면 실적 확인 시 상방 탄력이 커질 수 있습니다.",
      decision_read: "상승 추세가 거래량과 함께 재확인될 때 포지션을 증액하고, 과열권에서는 돌파 후 눌림을 우선합니다.",
      evidence_doc_ids: bullDocs,
    },
    {
      scenario: "Bear: 과열 해소 또는 기대치 미달",
      probability: "하방 리스크 시나리오",
      expected_outcome: [
        (rsiValue ?? 0) >= 70 ? `RSI ${formatMetricValue(rsi)} 과열권` : "모멘텀 둔화",
        volatility ? `변동성 ${formatMetricValue(volatility)}` : "",
        bear[0] || "실적/가이던스가 현재 기대를 충족하지 못하는 경우",
      ].filter(Boolean).join(" + "),
      asset_implication: "단기 평균선 이탈 또는 MACD 둔화가 동반되면 최근 상승분의 되돌림과 밸류에이션 압축 위험이 커집니다.",
      decision_read: "손절/감액 기준을 SMA20/50 이탈, MACD 음전환, 이벤트 후 가이던스 하향으로 명확히 둡니다.",
      evidence_doc_ids: bearDocs,
    },
  ];

  const strategies = [
    {
      strategy: "확인 매수 / 분할 진입",
      trigger: (d20 ?? 0) > 0 && (d50 ?? 0) > 0
        ? "가격이 SMA20/50 위에서 유지되고 MACD가 양수권을 유지할 때"
        : "가격이 단기 평균선을 회복하고 거래량이 평균 이상으로 동반될 때",
      rationale: "모멘텀은 방향성을 보여주지만 진입 가격의 기대값은 지지선 확인과 변동성 조절에서 결정됩니다.",
      risk_control: "RSI가 70 이상이면 추격 매수 비중을 줄이고, 눌림 또는 실적 확인 후 증액합니다.",
      evidence_doc_ids: baseDocs,
    },
    {
      strategy: "리스크 감액 / 무효화 기준",
      trigger: "SMA20/50 이탈, MACD 히스토그램 음전환, 또는 실적/가이던스가 현재 투자 가설을 훼손할 때",
      rationale: "기술적 추세가 약화되는 구간에서는 좋은 기업이어도 6~12개월 기대수익 대비 변동성 부담이 커집니다.",
      risk_control: "포지션 크기를 줄이고 다음 지지선 또는 새 펀더멘털 근거가 나올 때까지 재진입을 유보합니다.",
      evidence_doc_ids: bearDocs,
    },
  ];

  if ((m1 ?? 0) > 0 && (m3 ?? 0) < 0) {
    strategies.push({
      strategy: "중기 추세 복원 확인",
      trigger: "1개월 모멘텀은 유지되지만 3개월 모멘텀 또는 SMA200이 아직 약할 때",
      rationale: "단기 반등과 중기 추세 전환은 다른 신호입니다. SMA200 회복 또는 3개월 모멘텀 개선이 확인되어야 더 공격적인 비중 확대가 정당화됩니다.",
      risk_control: "장기 평균선 회복 전에는 목표 비중을 제한합니다.",
      evidence_doc_ids: collectMetricDocIds(metrics, [["3개월 가격 모멘텀"], ["sma200"]], evidenceFallback),
    });
  }

  return { scenarios, strategies };
}

function fallbackScenarioPackage(data) {
  const ticker = data?.ticker || data?.theme || "대상 자산";
  const docs = Array.isArray(data?.cited_doc_ids) ? data.cited_doc_ids.slice(0, 4) : [];
  const summary = cleanLine(data?.summary || data?.conclusion || "");
  return {
    scenarios: [
      {
        scenario: "Base: 확인된 근거 유지",
        probability: "기본 경로",
        expected_outcome: summary || `${ticker}의 현재 투자 가설은 확인된 근거가 유지되는지에 달려 있습니다.`,
        asset_implication: "가격은 기존 추세를 크게 벗어나기보다 핵심 지표와 이벤트 확인에 민감하게 반응할 가능성이 큽니다.",
        decision_read: "신규 진입은 분할로 제한하고, 핵심 지표가 같은 방향으로 정렬되는지 확인합니다.",
        evidence_doc_ids: docs,
      },
      {
        scenario: "Bull: 기대치 상향",
        probability: "상방 경로",
        expected_outcome: "실적, 수급, 정책 또는 기술적 모멘텀이 동시에 개선되면 시장 기대가 상향될 수 있습니다.",
        asset_implication: "상방 리레이팅은 단순 뉴스보다 가격 모멘텀, 거래량, 가이던스 개선이 함께 확인될 때 신뢰도가 높습니다.",
        decision_read: "상승 확인 후 눌림 또는 돌파 재확인 구간에서 비중 확대를 검토합니다.",
        evidence_doc_ids: docs,
      },
      {
        scenario: "Bear: 기대치 훼손",
        probability: "하방 경로",
        expected_outcome: "핵심 지표 둔화, 이벤트 실망, 유동성 악화가 겹치면 최근 가격 기대가 훼손될 수 있습니다.",
        asset_implication: "평균선 이탈, 모멘텀 둔화, 변동성 확대가 동반되면 손실 확대 가능성이 커집니다.",
        decision_read: "무효화 기준을 먼저 정하고, 손절 또는 감액 트리거를 지표 기반으로 집행합니다.",
        evidence_doc_ids: docs,
      },
    ],
    strategies: [
      {
        strategy: "조건부 분할 진입",
        trigger: "가격/모멘텀/거래량이 같은 방향으로 확인될 때",
        rationale: "근거가 완전히 정렬되지 않은 구간에서는 진입 단가와 변동성 관리가 기대수익을 좌우합니다.",
        risk_control: "초기 비중을 제한하고 핵심 지표가 훼손되면 추가 매수를 중단합니다.",
        evidence_doc_ids: docs,
      },
      {
        strategy: "무효화 기준 선집행",
        trigger: "주요 평균선 이탈, 모멘텀 음전환, 실적/정책 이벤트 실망",
        rationale: "방향성 판단보다 손실 제한 조건을 먼저 고정해야 포지션 관리가 일관됩니다.",
        risk_control: "사전에 정한 감액/손절 기준을 지표 기준일과 함께 기록합니다.",
        evidence_doc_ids: docs,
      },
    ],
  };
}

function renderQuantSnapshot(data) {
  if (!els.quantSnapshot) return;
  const extras = data?.execution_meta?.extras || {};
  const snapshot = extras.quant_snapshot || {};
  const metrics = getQuantMetrics(data, snapshot);
  const shockRows = snapshot.rate_shock_scenarios || snapshot.stress_scenarios || [];
  const exposures = snapshot.factor_exposures || {};
  els.quantSnapshot.innerHTML = "";

  if (!metrics.length && !Object.keys(snapshot).length) {
    els.quantSnapshot.innerHTML = `<div class="metric-empty">정량 snapshot이 없습니다. 수집 가능한 데이터가 부족하거나 종목/자산군에 맞는 deterministic engine이 아직 적용되지 않았습니다.</div>`;
    return;
  }

  const meta = document.createElement("div");
  meta.className = "quant-meta-grid";
  const metaRows = [
    ["asset_class", snapshot.asset_class || data?.mode || "—"],
    ["target", snapshot.target || data?.ticker || data?.theme || "—"],
    ["as_of", snapshot.as_of || "—"],
    ["freshness", snapshot.freshness_status || extras.data_freshness?.overall_status || "unknown"],
    ["source", snapshot.source || "deterministic_quant"],
  ];
  meta.innerHTML = metaRows
    .map(([k, v]) => `<div class="quant-meta"><span>${escapeHtml(k)}</span><strong>${escapeHtml(String(v || "—"))}</strong></div>`)
    .join("");
  els.quantSnapshot.appendChild(meta);

  const regimePanel = renderQuantRegime(data, metrics);
  if (regimePanel) els.quantSnapshot.appendChild(regimePanel);

  const tableWrap = document.createElement("div");
  tableWrap.className = "metric-table-wrap top-gap";
  const table = document.createElement("table");
  table.className = "metric-table";
  table.innerHTML = `<thead><tr><th>지표</th><th>값</th><th>단위</th><th>기준일</th><th>출처</th><th>상태</th><th>맥락</th></tr></thead><tbody></tbody>`;
  const tbody = table.querySelector("tbody");
  metrics.forEach((metric) => {
    const tr = document.createElement("tr");
    [
      metric.name,
      metric.value,
      metric.unit || "",
      metric.as_of || "unknown",
      metric.source || snapshot.source || "",
      metric.freshness_status || snapshot.freshness_status || "unknown",
      metric.context || "",
    ].forEach((value) => {
      const td = document.createElement("td");
      td.textContent = cleanLine(value) || "—";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  tableWrap.appendChild(table);
  els.quantSnapshot.appendChild(tableWrap);

  if (Array.isArray(shockRows) && shockRows.length) {
    const section = document.createElement("section");
    section.className = "quant-section";
    section.innerHTML = `<h4>Stress / Shock Table</h4>`;
    const shockTable = document.createElement("table");
    shockTable.className = "metric-table";
    const columns = Array.from(new Set(shockRows.flatMap((row) => Object.keys(row || {})))).slice(0, 8);
    shockTable.innerHTML = `<thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody></tbody>`;
    const shockBody = shockTable.querySelector("tbody");
    shockRows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((col) => {
        const td = document.createElement("td");
        td.textContent = cleanLine(row?.[col]) || "—";
        tr.appendChild(td);
      });
      shockBody.appendChild(tr);
    });
    section.appendChild(shockTable);
    els.quantSnapshot.appendChild(section);
  }

  if (exposures && typeof exposures === "object" && Object.keys(exposures).length) {
    const exposureBox = document.createElement("div");
    exposureBox.className = "quant-section";
    exposureBox.innerHTML = `<h4>Factor / Proxy Exposure</h4><pre class="mini-code">${escapeHtml(JSON.stringify(exposures, null, 2))}</pre>`;
    els.quantSnapshot.appendChild(exposureBox);
  }
}

function normalizeRiskItem(item, fallbackLabel = "리스크") {
  if (typeof item === "string") {
    return { label: fallbackLabel, title: cleanLine(item), body: "", evidence_doc_ids: [] };
  }
  const source = item && typeof item === "object" ? item : {};
  return {
    label: cleanLine(source.label || source.category || source.type || fallbackLabel),
    title: cleanLine(source.title || source.name || source.risk || source.text || source.scenario || source.strategy || fallbackLabel),
    body: cleanLine(source.body || source.description || source.context || source.impact || source.expected_outcome || source.rationale || ""),
    evidence_doc_ids: Array.isArray(source.evidence_doc_ids) ? source.evidence_doc_ids.filter(Boolean) : [],
  };
}

function collectRiskCards(data) {
  const extras = data?.execution_meta?.extras || {};
  const snapshot = extras.quant_snapshot || {};
  const cards = [];
  const metrics = getQuantMetrics(data, snapshot);
  const fallbackDocs = Array.isArray(data?.cited_doc_ids) ? data.cited_doc_ids.slice(0, 4) : [];
  const exposures = snapshot.factor_exposures || {};

  if (exposures && typeof exposures === "object" && (exposures.primary || Array.isArray(exposures.secondary))) {
    const primary = cleanLine(exposures.primary || "market_beta");
    const secondary = Array.isArray(exposures.secondary) ? exposures.secondary.map(cleanLine).filter(Boolean).join(", ") : cleanLine(exposures.secondary);
    cards.push({
      label: "Factor Exposure",
      title: `주요 노출: ${primary}`,
      body: secondary ? `보조 노출 축은 ${secondary}입니다. 같은 방향으로 악화되면 손실 분포가 비선형으로 커질 수 있습니다.` : "보조 노출 축이 제한적으로 확인됩니다.",
      evidence_doc_ids: fallbackDocs,
    });
  }

  const shockRows = firstNonEmptyArray(snapshot.stress_table, snapshot.rate_shock_scenarios).slice(0, 4);
  if (shockRows.length) {
    const shockText = shockRows.map((row) => {
      const shock = cleanLine(row.shock_bp !== undefined ? `${row.shock_bp}bp` : row.scenario || row.name || row.shock || "");
      const impact = cleanLine(row.estimated_price_impact_pct || row.impact || row.pnl || row.expected_move || "");
      return [shock, impact].filter(Boolean).join(" ");
    }).filter(Boolean).join(" / ");
    cards.push({
      label: "Stress / Shock",
      title: "민감도 기반 손실 구간",
      body: shockText || "스트레스 테이블은 존재하지만 표시 가능한 영향값이 제한적입니다.",
      evidence_doc_ids: fallbackDocs,
    });
  }

  const invalidation = firstNonEmptyArray(snapshot.regime?.invalidation_signals, extras.invalidation_signals).map(normalizeTextItem).filter(Boolean);
  if (invalidation.length) {
    cards.push({
      label: "Invalidation",
      title: "투자 가설 무효화 신호",
      body: invalidation.slice(0, 3).join(" / "),
      evidence_doc_ids: fallbackDocs,
    });
  }

  const volatility = findMetric(metrics, ["실현 변동성", "realized volatility"]);
  const rsi = findMetric(metrics, ["rsi"]);
  const sma20 = findMetric(metrics, ["sma20"]);
  const volValue = parseMetricNumber(volatility);
  const rsiValue = parseMetricNumber(rsi);
  if (volatility || rsi || sma20) {
    const pieces = [
      volatility ? `변동성 ${formatMetricValue(volatility)}` : "",
      rsi ? `RSI ${formatMetricValue(rsi)}` : "",
      sma20 ? `SMA20 괴리 ${formatMetricValue(sma20)}` : "",
    ].filter(Boolean);
    const body = [
      pieces.join(", "),
      (rsiValue ?? 0) >= 70 ? "과열권에서는 호재 반영 후 되돌림 리스크가 커집니다." : "",
      (volValue ?? 0) >= 30 ? "변동성 수준이 높아 포지션 크기와 손절 기준을 보수적으로 둬야 합니다." : "",
    ].filter(Boolean).join(" ");
    cards.push({
      label: "Technical Risk",
      title: "가격·변동성 리스크",
      body: body || "기술적 리스크 지표가 제한적으로 확인됩니다.",
      evidence_doc_ids: collectMetricDocIds(metrics, [["실현 변동성"], ["rsi"], ["sma20"]], fallbackDocs),
    });
  }

  firstNonEmptyArray(data?.key_risks, data?.bear_points, extras.key_risks)
    .map((item) => normalizeRiskItem(item, "Evidence-backed Risk"))
    .filter((item) => item.title)
    .slice(0, 4)
    .forEach((item) => cards.push(item));

  if (Array.isArray(snapshot.missing_axes) && snapshot.missing_axes.length) {
    cards.push({
      label: "Data Gap",
      title: "추가 확인이 필요한 데이터 축",
      body: snapshot.missing_axes.slice(0, 6).join(", "),
      evidence_doc_ids: [],
    });
  }

  return cards;
}

function renderRiskPanel(data) {
  if (!els.riskPanel) return;
  const extras = data?.execution_meta?.extras || {};
  const blocks = collectRiskCards(data);
  if (extras.error_type) blocks.unshift({ label: "오류/부분응답 분류", title: String(extras.error_type), body: "", evidence_doc_ids: [] });
  if (data?.uncertainty) blocks.unshift({ label: "불확실성", title: cleanLine(data.uncertainty), body: "", evidence_doc_ids: [] });
  if (Array.isArray(extras.blocking_missing_buckets) && extras.blocking_missing_buckets.length) {
    blocks.push({ label: "차단된 근거 버킷", title: extras.blocking_missing_buckets.join(", "), body: "", evidence_doc_ids: [] });
  }
  if (Array.isArray(extras.warning_missing_buckets) && extras.warning_missing_buckets.length) {
    blocks.push({ label: "경고 근거 버킷", title: extras.warning_missing_buckets.join(", "), body: "", evidence_doc_ids: [] });
  }
  if (data?.risk_management) {
    const risk = data.risk_management;
    if (Array.isArray(risk.main_risks) && risk.main_risks.length) {
      blocks.push({
        label: `Risk Management · ${risk.risk_level || "unknown"}`,
        title: risk.main_risks.slice(0, 3).map(cleanLine).filter(Boolean).join(" · "),
        body: cleanLine(risk.position_sizing_comment || ""),
        evidence_doc_ids: [],
      });
    }
    if (Array.isArray(risk.invalidating_conditions) && risk.invalidating_conditions.length) {
      blocks.push({
        label: "View Invalidation",
        title: risk.invalidating_conditions.slice(0, 3).map(cleanLine).filter(Boolean).join(" · "),
        body: "이 조건이 발생하면 기존 투자 판단을 재검토해야 합니다.",
        evidence_doc_ids: [],
      });
    }
  }
  if (data?.confidence_rationale) {
    const cr = data.confidence_rationale;
    const caps = Array.isArray(cr.caps_applied) ? cr.caps_applied : [];
    const fixed = (value) => Number(value || 0).toFixed(2);
    blocks.push({
      label: "Confidence Rationale",
      title: `final ${fixed(cr.final_confidence ?? data.confidence)} · evidence ${fixed(cr.evidence_coverage)} · numeric ${fixed(cr.numeric_grounding_rate)}`,
      body: caps.length ? caps.slice(0, 2).map(cleanLine).join(" · ") : "신뢰도 캡이 적용되지 않았거나 제한적입니다.",
      evidence_doc_ids: [],
    });
  }
  if (extras.data_freshness?.overall_status) blocks.push({ label: "데이터 신선도", title: extras.data_freshness.overall_status, body: "", evidence_doc_ids: [] });
  if (extras.validation_summary) blocks.push({ label: "검증 요약", title: JSON.stringify(extras.validation_summary), body: "", evidence_doc_ids: [] });

  els.riskPanel.innerHTML = "";
  if (!blocks.length) {
    els.riskPanel.innerHTML = `<div class="metric-empty">추가 리스크 진단 정보가 없습니다.</div>`;
    return;
  }
  blocks.slice(0, 12).forEach((block) => {
    const card = document.createElement("article");
    card.className = "risk-card";
    card.innerHTML = `
      <span>${escapeHtml(block.label || "Risk")}</span>
      <strong>${escapeHtml(block.title || "명시 없음")}</strong>
      ${block.body ? `<p>${escapeHtml(block.body)}</p>` : ""}
    `;
    const badges = document.createElement("div");
    badges.className = "evidence-chips";
    renderDocBadges(badges, block.evidence_doc_ids || []);
    card.appendChild(badges);
    els.riskPanel.appendChild(card);
  });
}

function firstNonEmptyArray(...values) {
  for (const value of values) {
    if (Array.isArray(value)) {
      const cleaned = value.filter((item) => {
        if (item === null || item === undefined) return false;
        if (typeof item === "string" || typeof item === "number") return Boolean(cleanLine(item));
        if (typeof item === "object") {
          return Object.values(item).some((inner) => {
            if (Array.isArray(inner)) return inner.length > 0;
            return Boolean(cleanLine(inner));
          });
        }
        return false;
      });
      if (cleaned.length) return cleaned;
    }
  }
  return [];
}

function normalizeScenarioItem(item) {
  if (typeof item === "string") {
    return {
      scenario: cleanLine(item),
      probability: "조건부",
      expected_outcome: cleanLine(item),
      asset_implication: "가격과 리스크 판단은 핵심 지표가 같은 방향으로 확인되는지에 따라 달라집니다.",
      evidence_doc_ids: [],
    };
  }
  const source = item && typeof item === "object" ? item : {};
  return {
    ...source,
    scenario: cleanLine(source.scenario || source.title || source.name || source.case || source.label) || "Scenario",
    probability: cleanLine(source.probability || source.trigger || source.condition || source.assumption) || "명시 없음",
    expected_outcome: cleanLine(source.expected_outcome || source.outcome || source.summary || source.thesis || source.view) || "명시 없음",
    asset_implication: cleanLine(source.asset_implication || source.market_impact || source.impact || source.implication || source.decision_read) || "명시 없음",
    decision_read: cleanLine(source.decision_read || source.action || source.strategy || source.decision),
    evidence_doc_ids: Array.isArray(source.evidence_doc_ids) ? source.evidence_doc_ids.filter(Boolean) : [],
  };
}

function normalizeStrategyItem(item) {
  if (typeof item === "string") {
    return {
      strategy: cleanLine(item),
      trigger: "핵심 지표 확인",
      rationale: cleanLine(item),
      risk_control: "포지션 크기와 손절 기준을 사전에 고정합니다.",
      evidence_doc_ids: [],
    };
  }
  const source = item && typeof item === "object" ? item : {};
  return {
    ...source,
    strategy: cleanLine(source.strategy || source.title || source.name || source.action || source.decision) || "Strategy",
    trigger: cleanLine(source.trigger || source.entry || source.condition || source.when) || "명시 없음",
    rationale: cleanLine(source.rationale || source.reason || source.thesis || source.why) || "명시 없음",
    risk_control: cleanLine(source.risk_control || source.risk_management || source.stop || source.invalidation) || "명시 없음",
    evidence_doc_ids: Array.isArray(source.evidence_doc_ids) ? source.evidence_doc_ids.filter(Boolean) : [],
  };
}

function scenarioBundleToArray(bundle) {
  if (!bundle || typeof bundle !== "object" || Array.isArray(bundle)) return [];
  const specs = [
    ["base_case", "Base Case"],
    ["bull_case", "Bull Case"],
    ["bear_case", "Bear Case"],
  ];
  return specs
    .map(([key, label]) => {
      const item = bundle[key];
      if (!item || typeof item !== "object") return null;
      return {
        scenario: label,
        probability: item.probability !== undefined && item.probability !== null ? String(item.probability) : "명시 없음",
        expected_outcome: cleanLine(item.thesis || item.expected_outcome || item.summary) || "명시 없음",
        asset_implication: [
          Array.isArray(item.drivers) && item.drivers.length ? `Drivers: ${item.drivers.map(cleanLine).filter(Boolean).join(" · ")}` : "",
          Array.isArray(item.risks) && item.risks.length ? `Risks: ${item.risks.map(cleanLine).filter(Boolean).join(" · ")}` : "",
        ].filter(Boolean).join(" / ") || "명시 없음",
        decision_read: cleanLine(item.thesis || ""),
        evidence_doc_ids: Array.isArray(item.evidence_doc_ids) ? item.evidence_doc_ids.filter(Boolean) : [],
      };
    })
    .filter(Boolean);
}

function scenarioSources(data) {
  const extras = data?.execution_meta?.extras || {};
  const bundled = scenarioBundleToArray(data?.scenario_analysis);
  if (bundled.length) return bundled.map(normalizeScenarioItem);
  return firstNonEmptyArray(
    data?.scenario_analysis,
    data?.fallback_scenario_analysis,
    extras.scenario_analysis,
    extras.fallback_scenario_analysis,
    extras.scenarios,
    extras.scenario_table,
    extras.quant_snapshot?.scenario_analysis
  ).map(normalizeScenarioItem);
}

function strategySources(data) {
  const extras = data?.execution_meta?.extras || {};
  return firstNonEmptyArray(
    data?.execution_strategy,
    data?.fallback_execution_strategy,
    extras.execution_strategy,
    extras.fallback_execution_strategy,
    extras.strategies,
    extras.execution_plan,
    extras.quant_snapshot?.execution_strategy
  ).map(normalizeStrategyItem);
}

function renderScenarioPanel(data) {
  if (!els.scenarioPanel) return;
  const existingScenarios = scenarioSources(data);
  const existingStrategies = strategySources(data);
  let derived = { scenarios: [], strategies: [] };
  if (!existingScenarios.length || !existingStrategies.length) {
    try {
      derived = deriveScenarioPackage(data);
    } catch (err) {
      console.warn("scenario derivation failed", err);
    }
  }
  if (!derived.scenarios.length || !derived.strategies.length) {
    const fallback = fallbackScenarioPackage(data);
    if (!derived.scenarios.length) derived.scenarios = fallback.scenarios;
    if (!derived.strategies.length) derived.strategies = fallback.strategies;
  }
  const scenarios = existingScenarios.length ? existingScenarios : derived.scenarios.map(normalizeScenarioItem);
  const strategies = existingStrategies.length ? existingStrategies : derived.strategies.map(normalizeStrategyItem);
  els.scenarioPanel.innerHTML = "";

  if (!scenarios.length && !strategies.length) {
    els.scenarioPanel.innerHTML = `<div class="metric-empty">시나리오/실행 전략이 생성되지 않았습니다.</div>`;
    return;
  }

  if (scenarios.length) {
    const grid = document.createElement("div");
    grid.className = "scenario-grid";
    scenarios.forEach((scenario) => {
      const card = document.createElement("article");
      card.className = "scenario-card";
      card.innerHTML = `
        <h4>${escapeHtml(scenario.scenario || scenario.title || "Scenario")}</h4>
        <p><strong>확률/조건:</strong> ${escapeHtml(scenario.probability || scenario.trigger || "명시 없음")}</p>
        <p><strong>예상 전개:</strong> ${escapeHtml(scenario.expected_outcome || "명시 없음")}</p>
        <p><strong>자산 영향:</strong> ${escapeHtml(scenario.asset_implication || scenario.decision_read || "명시 없음")}</p>
      `;
      const badges = document.createElement("div");
      badges.className = "evidence-chips";
      renderDocBadges(badges, scenario.evidence_doc_ids || []);
      card.appendChild(badges);
      grid.appendChild(card);
    });
    els.scenarioPanel.appendChild(grid);
  }

  if (strategies.length) {
    const section = document.createElement("section");
    section.className = "strategy-list top-gap";
    section.innerHTML = `<h4>Execution Strategy</h4>`;
    strategies.forEach((strategy) => {
      const item = document.createElement("article");
      item.className = "scenario-card";
      item.innerHTML = `
        <h4>${escapeHtml(strategy.strategy || strategy.title || "Strategy")}</h4>
        <p><strong>진입/트리거:</strong> ${escapeHtml(strategy.trigger || "명시 없음")}</p>
        <p><strong>근거:</strong> ${escapeHtml(strategy.rationale || "명시 없음")}</p>
        <p><strong>리스크 관리:</strong> ${escapeHtml(strategy.risk_control || "명시 없음")}</p>
      `;
      const badges = document.createElement("div");
      badges.className = "evidence-chips";
      renderDocBadges(badges, strategy.evidence_doc_ids || []);
      item.appendChild(badges);
      section.appendChild(item);
    });
    els.scenarioPanel.appendChild(section);
  }
}

function sectionLines(label, sections) {
  const lines = [label];
  if (!Array.isArray(sections) || !sections.length) {
    lines.push("- 식별된 항목 없음");
    return lines;
  }
  sections.forEach((section) => {
    if (section.title) lines.push(`- ${section.title}`);
    (section.bullets || []).forEach((bullet) => lines.push(`  - ${bullet}`));
    if (section.conclusion) lines.push(`  결론: ${section.conclusion}`);
  });
  return lines;
}

function formatTopicDecisionSections(data) {
  if (!data) return "";
  const lines = [];
  lines.push("핵심 분석");
  lines.push(...sectionLines("(1) 대상/주제 개요", data.asset_overview));
  lines.push(...sectionLines("(2) 거시/정책 환경", data.macro_regime));
  lines.push(...sectionLines("(3) 가격/시장 구조", data.rate_structure));

  if (Array.isArray(data.scenario_analysis) && data.scenario_analysis.length) {
    lines.push("(4) 시나리오 분석");
    data.scenario_analysis.forEach((scenario) => {
      lines.push(`- ${scenario.scenario || "Scenario"}${scenario.probability ? ` (${scenario.probability})` : ""}`);
      if (scenario.expected_outcome) lines.push(`  예상 전개: ${scenario.expected_outcome}`);
      if (scenario.asset_implication) lines.push(`  자산 영향: ${scenario.asset_implication}`);
      if (scenario.decision_read) lines.push(`  판단: ${scenario.decision_read}`);
    });
  } else {
    lines.push("(4) 시나리오 분석");
    lines.push("- 식별된 항목 없음");
  }

  lines.push("(5) 리스크 요인");
  lines.push(...listLines(data.key_risks));

  lines.push("(6) 촉매 및 실행 전략");
  if (Array.isArray(data.execution_strategy) && data.execution_strategy.length) {
    data.execution_strategy.forEach((strategy) => {
      lines.push(`- ${strategy.strategy || "Strategy"}`);
      if (strategy.trigger) lines.push(`  조건: ${strategy.trigger}`);
      if (strategy.rationale) lines.push(`  근거: ${strategy.rationale}`);
      if (strategy.risk_control) lines.push(`  리스크 관리: ${strategy.risk_control}`);
    });
  } else {
    lines.push("- 식별된 항목 없음");
  }

  lines.push("(7) 시장 가격 vs 현실");
  const pricingLines = [];
  (data.rate_structure || []).forEach((section) => {
    if (section.conclusion) pricingLines.push(section.conclusion);
  });
  (data.investment_judgment || []).forEach((section) => {
    if (section.conclusion) pricingLines.push(section.conclusion);
  });
  (data.scenario_analysis || []).slice(0, 2).forEach((scenario) => {
    if (scenario.decision_read || scenario.asset_implication) {
      pricingLines.push(`${scenario.scenario || "Scenario"}: ${scenario.decision_read || scenario.asset_implication}`);
    }
  });
  lines.push(...listLines(pricingLines, "가격 판단은 Quant 탭의 수치와 시나리오를 함께 확인해야 합니다."));

  lines.push("");
  lines.push("Synthesis (핵심 판단 구간)");
  lines.push(...listLines([data.core_thesis]));
  lines.push(...sectionLines("투자 판단", data.investment_judgment));

  lines.push("");
  lines.push("Decision Edge");
  lines.push("상방 동인");
  lines.push(...listLines(data.key_drivers));
  lines.push("하방 리스크");
  lines.push(...listLines(data.key_risks));
  if (Array.isArray(data.related_tickers) && data.related_tickers.length) {
    lines.push("관련 자산 / 표현 수단");
    lines.push(...listLines(data.related_tickers.map((t) => `${t.ticker} (${t.role}): ${t.rationale}`)));
  }
  if (data.uncertainty) {
    lines.push("불확실성");
    lines.push(`- ${data.uncertainty}`);
  }

  lines.push("");
  lines.push("결론");
  const conclusions = (data.investment_judgment || []).map((s) => s.conclusion).filter(Boolean);
  lines.push(...listLines(conclusions.length ? conclusions : [data.core_thesis]));
  return joinProseLines(dedupeReportLines(lines));
}

function formatEquityDecisionMemo(data) {
  if (!data || data.status === "failed") return data?.conclusion || "";
  const lines = [];
  const bull = Array.isArray(data.bull_points) ? data.bull_points : [];
  const bear = Array.isArray(data.bear_points) ? data.bear_points : [];
  const timeline = data.catalyst_timeline || {};
  const near = Array.isArray(timeline.near_term) ? timeline.near_term : [];
  const mid = Array.isArray(timeline.mid_term) ? timeline.mid_term : [];
  const long = Array.isArray(timeline.long_term) ? timeline.long_term : [];
  const bullishCatalysts = [...near, ...mid, ...long].filter((item) => /\[Bullish\]|상승|성장|수요|개선|beat|upside/i.test(item));
  const bearishCatalysts = [...near, ...mid, ...long].filter((item) => /\[Bearish\]|하락|리스크|압박|둔화|miss|downside/i.test(item));
  const macro = [...bull, ...bear, ...near, ...mid].filter((item) => /금리|연준|인플레이션|유동성|macro|rate|fed|inflation|liquidity/i.test(item));
  const ai = [...bull, ...bear].filter((item) => /AI|인공지능|cloud|클라우드|GPU|Copilot|OpenAI|Google|Amazon|AWS|Azure|NVIDIA/i.test(item));
  const cost = [...bull, ...bear].filter((item) => /margin|마진|cost|비용|capex|opex|hiring|구조조정/i.test(item));

  if (data.decision_view) {
    lines.push("Decision View");
    lines.push(`- Rating: ${data.decision_view.rating || "neutral"} · confidence ${data.decision_view.confidence ?? data.confidence ?? "—"}`);
    if (data.decision_view.decision_summary) lines.push(`- ${data.decision_view.decision_summary}`);
    if (data.decision_view.primary_thesis) lines.push(`- 핵심 논지: ${data.decision_view.primary_thesis}`);
    if (Array.isArray(data.decision_view.what_would_change_my_view) && data.decision_view.what_would_change_my_view.length) {
      lines.push("판단 변경 조건");
      lines.push(...listLines(data.decision_view.what_would_change_my_view));
    }
    lines.push("");
  }

  lines.push("핵심 분석");
  lines.push("(1) 거시 환경");
  lines.push(...listLines(macro, "수집 근거에서 거시 민감도가 직접 확인되지 않았습니다."));
  lines.push("(2) 사업 및 매출 동인");
  lines.push(...listLines(bull.slice(0, 4)));
  lines.push("(3) 비용 구조 및 마진");
  lines.push(...listLines(cost, "비용 구조와 마진 변화는 추가 실적/가이던스 확인이 필요합니다."));
  lines.push("(4) AI 전략 및 경쟁 포지션");
  lines.push(...listLines(ai, "AI가 핵심 투자 변수인지 현재 근거만으로는 확인되지 않습니다."));
  lines.push("(5) 리스크 요인");
  lines.push(...listLines(bear.slice(0, 4)));
  lines.push("(6) 촉매 요인 (단기 / 중기)");
  lines.push("상승 촉매");
  lines.push(...listLines(bullishCatalysts.length ? bullishCatalysts : bull.slice(0, 2)));
  lines.push("하락 촉매");
  lines.push(...listLines(bearishCatalysts.length ? bearishCatalysts : bear.slice(0, 2)));
  lines.push("(7) 시장 가격 vs 현실");
  lines.push(...metricLines(data.key_metrics));
  if (data.uncertainty) lines.push(`- 시장이 놓칠 수 있는 지점 / 근거 공백: ${data.uncertainty}`);
  lines.push("");
  lines.push("Synthesis (핵심 판단 구간)");
  lines.push(...listLines([data.conclusion]));
  lines.push("");
  lines.push("Decision Edge");
  lines.push("판단 체크포인트");
  lines.push(...listLines(data.open_questions || [], "추가 확인 질문 없음"));
  lines.push("");
  lines.push("결론");
  lines.push(...listLines([data.conclusion, data.uncertainty ? `판단 변경 조건: ${data.uncertainty}` : "판단 변경 조건: 다음 실적/가이던스와 핵심 리스크 트리거 확인"]));
  return joinProseLines(dedupeReportLines(lines));
}

function classifyResponseBanner(data, isFastPhase) {
  const extras = data?.execution_meta?.extras || {};
  const warnings = Array.isArray(extras.warnings) ? extras.warnings.filter(Boolean) : [];
  const errorType = extras.error_type || "";
  const friendlyByType = {
    validation_error: "입력 검증 오류입니다. 종목 모드에서는 ticker가 필요하고, ticker 없이 질문하려면 자동 또는 주제 모드를 사용하세요.",
    data_unavailable: "핵심 데이터 일부를 가져오지 못했습니다. 가능한 대체 데이터로 보수적 판단을 표시합니다.",
    evidence_sparse: "근거가 부족한 축이 있습니다. 누락된 데이터 축은 Diagnostics에서 확인하세요.",
    model_json_error: "모델의 구조화 JSON 출력이 불안정했습니다. 가능한 경우 로컬 정량/규칙 기반 보정 결과를 표시합니다.",
    model_language_error: "모델 출력 언어가 요청 기준을 위반했습니다. 한국어 우세 검증을 통과한 보정 결과만 사용해야 합니다.",
    provider_entitlement: "일부 유료/권한 필요 provider가 제한되었습니다. Yahoo/FRED/수집 문서 기반 대체 경로를 확인하세요.",
    infrastructure_error: "로컬 인프라 오류입니다. Ollama, Qdrant, 네트워크 상태를 확인하세요.",
    unknown_error: "분류되지 않은 오류입니다. Diagnostics와 서버 로그를 확인하세요.",
  };
  if (isFastPhase) {
    return {
      level: "info",
      message: data?.error_metadata || "초기 판단입니다. 심화 분석을 계속 진행합니다.",
    };
  }
  if (data?.status === "failed") {
    return { level: "error", message: friendlyByType[errorType] || data?.error_metadata || "요청이 실패했습니다." };
  }
  if (errorType === "validation_error") {
    return { level: "none", message: "" };
  }
  if (errorType && friendlyByType[errorType]) {
    return { level: errorType === "evidence_sparse" || errorType === "provider_entitlement" ? "warning" : "info", message: friendlyByType[errorType] };
  }
  if (data?.error_metadata) {
    return { level: "warning", message: data.error_metadata };
  }
  if (warnings.length) {
    return { level: "warning", message: warnings.join(" | ") };
  }
  if (data?.status === "partial") {
    return {
      level: "warning",
      message: data?.uncertainty || "일부 근거가 부족해 보수적으로 해석해야 합니다.",
    };
  }
  return { level: "none", message: "" };
}

function renderResponse(data, collection, request) {
  if (data && (data.mode === "sector_macro" || data.mode === "concept")) {
    const decisionMemo = formatTopicDecisionSections(data);
    const decisionView = data.decision_view
      ? `Decision View\n- Rating: ${data.decision_view.rating || "neutral"} · confidence ${data.decision_view.confidence ?? "—"}\n- ${data.decision_view.decision_summary || ""}\n- 핵심 논지: ${data.decision_view.primary_thesis || ""}`
      : "";
    const uncertainty = data.uncertainty ? `불확실성\n${data.uncertainty}` : "";
    const keyMetrics = Array.isArray(data.key_metrics) && data.key_metrics.length
      ? `핵심 지표\n${data.key_metrics.map(formatMetricLine).filter(Boolean).map((line) => `- ${line}`).join("\n")}`
      : "";
    const related = Array.isArray(data.related_tickers) && data.related_tickers.length
      ? `관련 종목\n${data.related_tickers.map((t) => `- ${t.ticker} (${t.role}): ${t.rationale}`).join("\n")}`
      : "";
    data = {
      ...data,
      ticker: data.theme || "TOPIC",
      summary: buildTopicHeadlineSummary(data),
      conclusion: buildTopicDecisionMemo(data, decisionView, decisionMemo, uncertainty, keyMetrics, related),
      sentiment: "Neutral",
      confidence: data.decision_view?.confidence ?? data.confidence ?? data.confidence_rationale?.final_confidence ?? 0,
      bull_points: (data.key_drivers || []).map((d) => d.text || String(d)),
      bear_points: (data.key_risks || []).map((d) => d.text || String(d)),
      bull_evidence_ids: (data.key_drivers || []).map((d) => d.evidence_doc_ids || []),
      bear_evidence_ids: (data.key_risks || []).map((d) => d.evidence_doc_ids || []),
    };
  }
  const phase = data?.execution_meta?.extras?.phase || "final";
  const isFastPhase = phase === "fast";
  state.lastResponse = data;
  state.lastCollection = collection;
  state.lastRequest = request;

  els.emptyState.classList.add("hidden");
  els.loadingState.classList.add("hidden");
  els.resultView.classList.remove("hidden");
  if (els.compareView) els.compareView.classList.add("hidden");

  // Header
  els.resTicker.textContent = data.ticker || "";
  els.resStatus.textContent = isFastPhase ? "INITIAL" : (data.status || "").toUpperCase();
  els.resStatus.className = `status-badge ${statusClass(data.status)}`;
  els.resQuestion.textContent = data.question || "";

  if (els.resCacheBadge) {
    const cacheHit = collection?.cache_hit ?? data?.execution_meta?.extras?.cache_hit;
    const cacheAge = collection?.cache_age_s ?? 0;
    const cacheLabel = cacheAge ? `cache · ${formatAge(cacheAge)}` : "cache · reused";
    const hit = !!cacheHit;
    if (hit) {
      els.resCacheBadge.textContent = cacheLabel;
      els.resCacheBadge.classList.remove("hidden");
    } else {
      els.resCacheBadge.classList.add("hidden");
    }
  }

  // Error / warning banner
  const banner = classifyResponseBanner(data, isFastPhase);
  if (banner.level === "none") {
    els.errorBanner.classList.add("hidden");
    els.errorBanner.classList.remove("failed", "warning", "info");
  } else {
    els.errorBanner.textContent = banner.message;
    els.errorBanner.classList.remove("hidden");
    els.errorBanner.classList.toggle("failed", banner.level === "error");
    els.errorBanner.classList.toggle("warning", banner.level === "warning");
    els.errorBanner.classList.toggle("info", banner.level === "info");
  }

  // KPIs
  const sentiment = data.sentiment || "Neutral";
  els.resSentiment.textContent = sentiment;
  els.resSentiment.className = "kpi-value " + sentimentTone(sentiment);

  const conf = Number(data.confidence || 0);
  els.resConfidence.textContent = conf.toFixed(2);
  els.confidenceFill.style.width = `${Math.max(0, Math.min(1, conf)) * 100}%`;

  els.resCitationCount.textContent = (data.citations || []).length;
  els.resChunkCount.textContent = (data.raw_context || []).length;

  // Tabs content
  renderProse(els.resSummary, data.summary || "—");
  const isTopicMode = data && (data.mode === "sector_macro" || data.mode === "concept");
  renderProse(els.resConclusion, (isTopicMode ? data.conclusion : formatEquityDecisionMemo(data) || data.conclusion) || "—");

  // Evidence must be indexed before Bull/Bear render so chips can resolve titles.
  renderEvidence(data.raw_context || []);
  renderMetricTable(data.key_metrics || []);
  renderQuantSnapshot(data);
  renderRiskPanel(data);
  renderScenarioPanel(data);
  renderBullBear(
    data.bull_points || [],
    data.bear_points || [],
    data.bull_evidence_ids || [],
    data.bear_evidence_ids || []
  );
  renderCitations(data.citations || []);
  renderDiagnostics(request, collection);
  renderExecutionMeta(data.execution_meta || null);
  renderRaw(data);
  setExportAvailability(!isFastPhase && !!state.lastResponse && data.status !== "failed");
  if (isFastPhase) {
    els.reportMd.textContent = "# 최종 보고서 생성 중입니다.";
  } else {
    fetchMarkdownReport();
  }
}

function renderFailure(request, message) {
  const synthetic = {
    ticker: request.ticker,
    question: request.question,
    status: "failed",
    error_metadata: message,
    summary: "요청이 실패했습니다.",
    sentiment: "Neutral",
    confidence: 0,
    conclusion: "서버 또는 파이프라인 오류입니다. 로그를 확인해주세요.",
    citations: [],
    raw_context: [],
    bull_points: [],
    bear_points: [],
  };
  renderResponse(synthetic, null, request);
}

function sentimentTone(s) {
  const key = (s || "").toLowerCase();
  if (["positive", "bullish"].includes(key)) return "pos";
  if (["negative", "bearish"].includes(key)) return "neg";
  return "neu";
}

function renderBullBear(bull, bear, bullEv, bearEv) {
  const evidenceIndex = buildEvidenceIndex(state.evidenceRaw);

  const fill = (ul, items, evidence, emptyMsg) => {
    ul.innerHTML = "";
    if (!items.length) {
      ul.innerHTML = `<li class="muted">${emptyMsg}</li>`;
      return;
    }
    items.forEach((p, i) => {
      const text = typeof p === "string" ? p : (p.text || JSON.stringify(p));
      const ids = Array.isArray(evidence) && Array.isArray(evidence[i]) ? evidence[i] : [];
      const li = document.createElement("li");
      const textDiv = document.createElement("div");
      textDiv.className = "tpoint-text";
      textDiv.textContent = text;
      li.appendChild(textDiv);
      if (ids.length) {
        const chipRow = document.createElement("div");
        chipRow.className = "evidence-chips";
        ids.forEach((docId) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "evidence-chip";
          const item = evidenceIndex.get(String(docId));
          const label = item ? (item.title || docId) : docId;
          chip.textContent = item ? truncateLabel(label, 34) : `doc ${truncateLabel(docId, 14)}`;
          chip.title = item ? `${item.source || "doc"} · ${item.date || ""}\n${label}` : `doc_id: ${docId}`;
          chip.addEventListener("click", () => jumpToEvidence(docId));
          chipRow.appendChild(chip);
        });
        li.appendChild(chipRow);
      } else {
        const note = document.createElement("div");
        note.className = "evidence-note";
        note.textContent = "근거 링크 없음";
        li.appendChild(note);
      }
      ul.appendChild(li);
    });
  };
  fill(els.bullList, bull, bullEv, "식별된 상승 촉매 없음");
  fill(els.bearList, bear, bearEv, "식별된 하락 리스크 없음");
}

function buildEvidenceIndex(items) {
  const map = new Map();
  (items || []).forEach((it, idx) => {
    const docId = (it && it.metadata && it.metadata.doc_id) || it?.doc_id || it?.id;
    if (docId) map.set(String(docId), { ...it, _index: idx });
  });
  return map;
}

function truncateLabel(text, n) {
  const s = String(text || "");
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function jumpToEvidence(docId) {
  const evidenceTab = document.querySelector('.tab[data-tab="evidence"]');
  if (evidenceTab) evidenceTab.click();
  els.evidenceSearch.value = "";
  applyEvidenceFilter();
  setTimeout(() => {
    const target = els.evidenceList.querySelector(`[data-doc-id="${CSS.escape(String(docId))}"]`);
    if (target) {
      target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("highlight");
      setTimeout(() => target.classList.remove("highlight"), 1400);
    }
  }, 60);
}

function renderEvidence(items) {
  state.evidenceRaw = items;
  applyEvidenceFilter();
}

function applyEvidenceFilter() {
  const q = (els.evidenceSearch.value || "").toLowerCase().trim();
  const items = state.evidenceRaw.filter((it) => {
    if (!q) return true;
    return (
      (it.title || "").toLowerCase().includes(q) ||
      (it.chunk || "").toLowerCase().includes(q) ||
      (it.source || "").toLowerCase().includes(q)
    );
  });
  els.evidenceList.innerHTML = "";
  if (!items.length) {
    els.evidenceList.innerHTML = `<li class="muted" style="padding:14px;color:var(--text-mute);font-size:12px;">근거 컨텍스트가 없습니다.</li>`;
    return;
  }
  items.forEach((it, idx) => {
    const li = document.createElement("details");
    li.className = "evidence-item";
    if (idx < 2) li.open = true;
    const docId = (it && it.metadata && it.metadata.doc_id) || it.doc_id || it.id || "";
    if (docId) li.dataset.docId = String(docId);
    const score = typeof it.score === "number" ? it.score.toFixed(3) : "—";
    li.innerHTML = `
      <summary>
        <span class="ev-source">${escapeHtml(it.source || "doc")}</span>
        <span class="ev-title">${escapeHtml(it.title || "Untitled")}</span>
        <span class="ev-date">${escapeHtml(it.date || "")}</span>
        <span class="ev-score">score ${score}</span>
      </summary>
      <div class="ev-body">${escapeHtml(it.chunk || "")}</div>
    `;
    els.evidenceList.appendChild(li);
  });
}

function renderCitations(cits) {
  els.citationsList.innerHTML = "";
  if (!cits.length) {
    els.citationsList.innerHTML = `<li style="color:var(--text-mute);font-family:inherit;">인용된 자료가 없습니다.</li>`;
    return;
  }
  cits.forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="cit-source">${escapeHtml(c.source || "")}</span>
      <span class="cit-title">${escapeHtml(c.title || "")}</span>
      <span class="cit-date">${escapeHtml(c.date || "")}</span>
    `;
    els.citationsList.appendChild(li);
  });
}

function kvPairs(container, obj) {
  container.innerHTML = "";
  if (!obj) {
    container.innerHTML = `<span class="k">—</span><span class="v">데이터 없음</span>`;
    return;
  }
  Object.entries(obj).forEach(([k, v]) => {
    const kEl = document.createElement("span"); kEl.className = "k"; kEl.textContent = k;
    const vEl = document.createElement("span"); vEl.className = "v";
    vEl.textContent = typeof v === "object" ? JSON.stringify(v) : String(v);
    container.appendChild(kEl); container.appendChild(vEl);
  });
}

function renderDiagnostics(request, collection) {
  kvPairs(els.diagRequest, request ? {
    ticker: request.ticker,
    question: request.question,
    mode_hint: request.mode_hint,
    intent_kind: request.intent_kind,
    extracted_ticker: request.extracted_ticker || "",
    route_hint: request.route_hint,
    sources: (request.sources || []).join(", "),
    lookback_days: request.lookback_days,
    top_k: request.top_k,
    model: request.model,
  } : null);

  els.sourceResultsBody.innerHTML = "";
  els.providerResultsBody.innerHTML = "";

  if (!collection) {
    const noData = `<tr><td colspan="5" style="color:var(--text-mute);">수집 진단 데이터 없음</td></tr>`;
    els.sourceResultsBody.innerHTML = noData;
    els.providerResultsBody.innerHTML = noData;
    kvPairs(els.diagRetrieval, null);
    return;
  }

  (collection.source_results || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.source)}</td>
      <td><span class="st ${sourceStatusClass(r.status)}">${escapeHtml(r.status)}</span></td>
      <td>${escapeHtml(String(r.doc_count ?? 0))}</td>
      <td>${escapeHtml(String(r.elapsed_s ?? "—"))}s</td>
      <td>${escapeHtml(r.detail || "")}</td>
    `;
    els.sourceResultsBody.appendChild(tr);
  });

  (collection.provider_results || []).forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(r.source)}</td>
      <td><span class="st ${sourceStatusClass(r.status)}">${escapeHtml(r.status)}</span></td>
      <td>${escapeHtml(String(r.doc_count ?? 0))}</td>
      <td>${escapeHtml(String(r.elapsed_s ?? "—"))}s</td>
      <td>${escapeHtml(r.detail || "")}</td>
    `;
    els.providerResultsBody.appendChild(tr);
  });

  kvPairs(els.diagRetrieval, {
    run_started_at: collection.run_started_at || "—",
    freshness_cutoff: collection.freshness_cutoff || "—",
    retrieval_policy: collection.retrieval_policy || "—",
    current_doc_ids: (collection.current_doc_ids || []).length,
    lookback_days: collection.lookback_days || "—",
    cache_hit: collection.cache_hit ? `yes · ${formatAge(collection.cache_age_s)} old` : "no",
    cached_at: collection.cached_at || "—",
  });
}

function formatAge(sec) {
  const s = Number(sec || 0);
  if (!s || s <= 0) return "0s";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

const STAGE_ORDER = ["collect", "ingest", "retrieve", "infer", "analyze", "report", "output"];

function renderExecutionMeta(meta) {
  if (!els.diagInference) return;
  if (!meta || typeof meta !== "object") {
    kvPairs(els.diagInference, null);
    els.stageTimeline.innerHTML = "";
    return;
  }
  const extras = meta.extras || {};
  const formatGate = (gate) => {
    if (!gate || typeof gate !== "object") return "—";
    if (gate.ok === true) return "ok";
    const missing = gate.completeness?.missing;
    if (!missing || typeof missing !== "object") return "not_ok";
    const short = Object.entries(missing)
      .filter(([, value]) => Number(value || 0) > 0)
      .map(([key, value]) => `${key}:${value}`)
      .join(", ");
    return short || "not_ok";
  };
  const shown = {
    primary_model: meta.primary_model || "—",
    producing_model: meta.producing_model || "—",
    fallback_used: meta.fallback_used === null || meta.fallback_used === undefined ? "—" : String(meta.fallback_used),
    fallback_available: meta.fallback_available === null || meta.fallback_available === undefined ? "—" : String(meta.fallback_available),
    retry_count: meta.retry_count ?? "—",
    total_latency_s: meta.total_latency_s ?? "—",
    pipeline_latency_s: meta.pipeline_latency_s ?? "—",
    prompt_char_count: meta.prompt_char_count ?? "—",
    chunks_used: meta.chunks_used ?? "—",
    lens: meta.lens || "—",
    context_horizon: meta.context_horizon || "—",
    phase: extras.phase || "—",
    retrieval_mode: extras.retrieval_mode || "—",
    cache_hit: extras.cache_hit === null || extras.cache_hit === undefined ? "—" : String(extras.cache_hit),
    ingest_skipped_docs: extras.ingest_skipped_docs ?? "—",
    deep_pass_skipped: extras.deep_pass_skipped === null || extras.deep_pass_skipped === undefined ? "—" : String(extras.deep_pass_skipped),
    deep_pass_reason: Array.isArray(extras.deep_pass_reason) ? (extras.deep_pass_reason.join(", ") || "—") : (extras.deep_pass_reason || "—"),
    warnings: Array.isArray(extras.warnings) ? (extras.warnings.join(" | ") || "—") : (extras.warnings || "—"),
    blocking_evidence_buckets: Array.isArray(extras.blocking_evidence_buckets) ? (extras.blocking_evidence_buckets.join(", ") || "—") : (extras.blocking_evidence_buckets || "—"),
    warning_evidence_buckets: Array.isArray(extras.warning_evidence_buckets) ? (extras.warning_evidence_buckets.join(", ") || "—") : (extras.warning_evidence_buckets || "—"),
    blocking_missing_buckets: Array.isArray(extras.blocking_missing_buckets) ? (extras.blocking_missing_buckets.join(", ") || "—") : (extras.blocking_missing_buckets || "—"),
    warning_missing_buckets: Array.isArray(extras.warning_missing_buckets) ? (extras.warning_missing_buckets.join(", ") || "—") : (extras.warning_missing_buckets || "—"),
    substituted_buckets: Array.isArray(extras.substituted_buckets) ? (extras.substituted_buckets.join(", ") || "—") : (extras.substituted_buckets || "—"),
    error_type: extras.error_type || "—",
    data_freshness: extras.data_freshness || "—",
    provider_status: extras.provider_status || "—",
    model_capabilities: extras.model_capabilities || "—",
    validation_summary: extras.validation_summary || "—",
    retrieval_plan: extras.retrieval_plan || "—",
    quality_metrics: extras.quality_metrics || "—",
    numeric_grounding_warnings: Array.isArray(extras.numeric_grounding_warnings) ? (extras.numeric_grounding_warnings.join(" | ") || "—") : (extras.numeric_grounding_warnings || "—"),
    confidence_caps: Array.isArray(extras.confidence_caps) ? (extras.confidence_caps.join(" | ") || "—") : (extras.confidence_caps || "—"),
    run_manifest: extras.run_manifest || "—",
    fast_gate: formatGate(extras.fast_gate),
    final_gate: formatGate(extras.final_gate),
  };
  kvPairs(els.diagInference, shown);

  els.stageTimeline.innerHTML = "";
  const stageTimings = extras.stage_timings || {};
  const normalizeStage = (name) => {
    const raw = String(name || "");
    if (raw.startsWith("retrieve")) return "retrieve";
    if (raw.startsWith("infer")) return "infer";
    return raw;
  };
  const ran = new Set(Array.isArray(meta.stages_ran) ? meta.stages_ran : []);
  Object.keys(stageTimings).forEach((name) => ran.add(normalizeStage(name)));
  STAGE_ORDER.forEach((name) => {
    const durations = Object.entries(stageTimings)
      .filter(([key]) => normalizeStage(key) === name)
      .map(([, value]) => `${value}s`);
    const pill = document.createElement("span");
    pill.className = "stage-pill " + (ran.has(name) ? "ran" : "skipped");
    pill.textContent = durations.length ? `${name} ${durations.join(" / ")}` : name;
    els.stageTimeline.appendChild(pill);
  });
}

function renderRaw(data) {
  els.rawJson.textContent = JSON.stringify(data, null, 2);
}

async function fetchMarkdownReport() {
  try {
    const res = await fetch(API.reportMd);
    if (res.ok) {
      els.reportMd.textContent = await res.text();
    } else {
      els.reportMd.textContent = "# Report not available yet.";
    }
  } catch {
    els.reportMd.textContent = "# Report not available.";
  }
}

// ---------- Tabs ----------
function bindTabs() {
  els.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      els.tabs.forEach((t) => t.classList.toggle("active", t === tab));
      els.tabPanels.forEach((p) => p.classList.toggle("active", p.dataset.panel === target));
    });
  });
}

// ---------- Downloads ----------
function downloadBlob(name, text, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
}

function bindDownloads() {
  els.downloadMdBtn.addEventListener("click", async () => {
    try {
      const res = await fetch(API.reportMd);
      const text = res.ok ? await res.text() : els.reportMd.textContent;
      const ticker = state.lastResponse?.ticker || "report";
      downloadBlob(`fingpt_${ticker}_${Date.now()}.md`, text, "text/markdown");
    } catch (e) { alert("Markdown 다운로드 실패: " + e.message); }
  });

  els.downloadJsonBtn.addEventListener("click", () => {
    if (!state.lastResponse) return;
    const ticker = state.lastResponse.ticker || "response";
    downloadBlob(`fingpt_${ticker}_${Date.now()}.json`, JSON.stringify(state.lastResponse, null, 2), "application/json");
  });

  els.openHtmlBtn.addEventListener("click", () => {
    window.open(API.reportHtml, "_blank", "noopener");
  });

  const exportToggle = document.getElementById("exportToggleBtn");
  const exportMenu = document.getElementById("exportMenu");
  if (exportToggle && exportMenu) {
    exportToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      exportMenu.classList.toggle("hidden");
    });
    // Dismiss when clicking anywhere outside — feels native without managing focus.
    document.addEventListener("click", (e) => {
      if (!exportMenu.classList.contains("hidden") && !exportMenu.contains(e.target) && e.target !== exportToggle) {
        exportMenu.classList.add("hidden");
      }
    });
    exportMenu.querySelectorAll("button[data-export]").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        exportMenu.classList.add("hidden");
        const kind = btn.dataset.export;
        try {
          await runExport(kind);
        } catch (err) {
          alert(`Export 실패: ${err.message || err}`);
        }
      });
    });
  }
}

async function runExport(kind) {
  if (!state.lastResponse) {
    alert("먼저 분석을 실행하거나 히스토리에서 불러오세요.");
    return;
  }
  // kind => endpoint + query string. The server reads the latest archived
  // response when run_id is omitted, so single-runs just work.
  let url, filename, mime;
  const ticker = state.lastResponse.ticker || "analysis";
  const stamp = Date.now();
  if (kind === "csv") {
    url = "/api/v1/outputs/export/csv";
    filename = `fingpt_${ticker}_${stamp}.csv`;
    mime = "text/csv";
  } else if (kind === "jsonl") {
    url = "/api/v1/outputs/export/jsonl?include_raw_context=true";
    filename = `fingpt_${ticker}_${stamp}.jsonl`;
    mime = "application/x-ndjson";
  } else if (kind === "jsonl-lean") {
    url = "/api/v1/outputs/export/jsonl?include_raw_context=false";
    filename = `fingpt_${ticker}_${stamp}_lean.jsonl`;
    mime = "application/x-ndjson";
  } else {
    return;
  }
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${detail.slice(0, 160)}`);
  }
  const text = await res.text();
  downloadBlob(filename, text, mime);
}

// ---------- Load latest ----------
async function loadLatest() {
  try {
    const res = await fetch(API.latest);
    if (!res.ok) throw new Error("no data");
    const blob = await res.json();
    if (!blob.response) {
      alert("이전 실행 결과를 찾을 수 없습니다. 먼저 한 번 분석을 실행하세요.");
      return;
    }
    renderResponse(blob.response, blob.collection || null, blob.request || null);
  } catch (e) {
    alert("최신 결과 로드 실패: " + e.message);
  }
}

// ---------- Bindings ----------
function bindInputs() {
  els.tickerChips.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const chipTicker = btn.dataset.ticker;
      if (els.compareMode && els.compareMode.checked) {
        const current = els.ticker.value
          .split(/[\s,]+/)
          .map((t) => t.trim().toUpperCase())
          .filter(Boolean);
        if (!current.includes(chipTicker)) current.push(chipTicker);
        els.ticker.value = current.join(", ");
      } else {
        els.ticker.value = chipTicker;
      }
      els.ticker.focus();
      persistForm();
    });
  });
  if (els.compareMode) {
    els.compareMode.addEventListener("change", () => {
      updateCompareModeUI();
      setFormNotice("");
      persistForm();
    });
    updateCompareModeUI();
  }
  els.ticker.addEventListener("input", () => { setFormNotice(""); persistForm(); });
  els.researchModeInputs().forEach((i) => i.addEventListener("change", () => {
    updateCompareModeUI();
    setFormNotice("");
    persistForm();
  }));
  els.question.addEventListener("input", () => { setFormNotice(""); persistForm(); });
  els.model.addEventListener("change", persistForm);
  els.sourceInputs().forEach((i) => i.addEventListener("change", persistForm));

  els.lookback.addEventListener("input", () => {
    els.lookback.dataset.dirty = "1";
    updateRangeLabels(); persistForm();
  });
  els.topk.addEventListener("input", () => {
    els.topk.dataset.dirty = "1";
    updateRangeLabels(); persistForm();
  });

  els.form.addEventListener("submit", runAnalysis);

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });

  els.loadLatestBtn.addEventListener("click", loadLatest);
  if (els.homeBtn) els.homeBtn.addEventListener("click", showHome);
  if (els.marketDashboardTab) {
    els.marketDashboardTab.addEventListener("click", () => setDashboardTab("market"));
  }
  if (els.quantLabTab) {
    els.quantLabTab.addEventListener("click", () => setDashboardTab("quant"));
  }
  if (els.homeNewsRefresh) els.homeNewsRefresh.addEventListener("click", () => {
    loadDashboardNews(true);
    loadDashboardMarket(true);
    loadDashboardEquityHeatmap(true);
    loadDataHealth(true);
    initializeTradingViewDashboard(true);
  });
  if (els.homeHeatmapRefresh) els.homeHeatmapRefresh.addEventListener("click", () => loadDashboardEquityHeatmap(true));
  if (els.dataHealthRefresh) els.dataHealthRefresh.addEventListener("click", () => loadDataHealth(true));
  if (els.assetDetailLoad) els.assetDetailLoad.addEventListener("click", loadAssetDetail);
  if (els.quantFeatureRun) els.quantFeatureRun.addEventListener("click", runQuantFeaturePreview);
  if (els.quantSignalRun) els.quantSignalRun.addEventListener("click", runQuantSignalPreview);
  if (els.quantStrategyRefresh) els.quantStrategyRefresh.addEventListener("click", () => loadQuantStrategies(true));
  if (els.quantStrategyNewDraft) els.quantStrategyNewDraft.addEventListener("click", () => {
    setStrategyEditor(quantStrategyDraftFromControls());
    showQuantStrategyMessage("현재 퀀트 랩 조건으로 전략 초안을 만들었습니다.", "success");
  });
  if (els.quantStrategyDryRun) els.quantStrategyDryRun.addEventListener("click", () => runQuantStrategyDryRun());
  if (els.quantStrategySave) els.quantStrategySave.addEventListener("click", saveQuantStrategy);
  if (els.quantStrategyDelete) els.quantStrategyDelete.addEventListener("click", () => deleteQuantStrategy());
  if (els.quantRunHistoryRefresh) els.quantRunHistoryRefresh.addEventListener("click", () => loadQuantRunHistory(true));
  if (els.quantExportStorageReport) els.quantExportStorageReport.addEventListener("click", loadQuantExportStorageReport);
  if (els.quantCrossRunCleanupPreview) els.quantCrossRunCleanupPreview.addEventListener("click", () => previewCrossRunExportCleanup(1, 0));
  if (els.quantRunHistorySurface) {
    els.quantRunHistorySurface.addEventListener("click", (event) => {
      const rawTarget = event.target;
      const target = rawTarget?.closest ? rawTarget.closest("[data-action]") : rawTarget;
      if (target && target.dataset && target.dataset.action === "cross-run-cleanup-preview") {
        previewCrossRunExportCleanup(target.dataset.keepLast || 1, target.dataset.staleAfterDays || 0);
      }
      if (target && target.dataset && target.dataset.action === "cross-run-cleanup-apply") {
        applyCrossRunExportCleanup();
      }
    });
  }
  if (els.backtestRun) els.backtestRun.addEventListener("click", runHomeBacktest);
  if (els.backtestTicker) els.backtestTicker.addEventListener("input", renderBacktestUniverseChips);
  if (els.backtestUniverseOpen) els.backtestUniverseOpen.addEventListener("click", openSymbolPicker);
  if (els.backtestStrategy) {
    els.backtestStrategy.addEventListener("change", () => {
      state.activeStrategyId = "";
      if (els.backtestStrategyRegistry) els.backtestStrategyRegistry.value = "";
    });
  }
  if (els.backtestStrategyRegistry) {
    els.backtestStrategyRegistry.addEventListener("change", () => {
      const strategyId = els.backtestStrategyRegistry.value || "";
      if (!strategyId) {
        state.activeStrategyId = "";
        return;
      }
      loadQuantStrategyDetail(strategyId);
    });
  }
  if (els.symbolPickerClose) els.symbolPickerClose.addEventListener("click", closeSymbolPicker);
  if (els.symbolPickerApply) els.symbolPickerApply.addEventListener("click", closeSymbolPicker);
  if (els.symbolPickerClear) {
    els.symbolPickerClear.addEventListener("click", () => {
      setBacktestUniverse([]);
      renderSymbolPicker();
    });
  }
  if (els.symbolPickerSearch) els.symbolPickerSearch.addEventListener("input", renderSymbolPicker);
  if (els.symbolPickerCountry) els.symbolPickerCountry.addEventListener("change", renderSymbolPicker);
  if (els.symbolPickerSector) els.symbolPickerSector.addEventListener("change", renderSymbolPicker);
  if (els.symbolPickerTabs) {
    els.symbolPickerTabs.addEventListener("click", (event) => {
      const rawTarget = event.target;
      const target = rawTarget?.closest ? rawTarget.closest("[data-symbol-type]") : rawTarget;
      if (!target?.dataset?.symbolType) return;
      state.symbolPickerType = target.dataset.symbolType || "all";
      els.symbolPickerTabs.querySelectorAll("[data-symbol-type]").forEach((button) => {
        button.classList.toggle("active", button === target);
      });
      renderSymbolPicker();
    });
  }
  if (els.symbolPickerList) {
    els.symbolPickerList.addEventListener("click", (event) => {
      const rawTarget = event.target;
      const target = rawTarget?.closest ? rawTarget.closest("[data-symbol-toggle]") : rawTarget;
      if (target?.dataset?.symbolToggle) toggleSymbolPickerItem(target.dataset.symbolToggle);
    });
  }
  if (els.symbolPickerModal) {
    els.symbolPickerModal.addEventListener("click", (event) => {
      if (event.target === els.symbolPickerModal) closeSymbolPicker();
    });
  }
  if (els.backtestSurface) {
    els.backtestSurface.addEventListener("click", (event) => {
      const rawTarget = event.target;
      const target = rawTarget?.closest ? rawTarget.closest("[data-action]") : rawTarget;
      if (target && target.dataset && target.dataset.action === "sync-backtest-portfolio") {
        syncPortfolioFromBacktest();
      }
      if (target && target.dataset && target.dataset.action === "replay-backtest") {
        runQuantBacktestReplay(target.dataset.runId || "");
      }
      if (target && target.dataset && target.dataset.action === "replay-reports") {
        loadQuantReplayReports(target.dataset.runId || "");
      }
      if (target && target.dataset && target.dataset.action === "export-backtest") {
        exportQuantBacktestArtifact(target.dataset.runId || "", target.dataset.format || "jsonl");
      }
      if (target && target.dataset && target.dataset.action === "export-history") {
        loadQuantExportHistory(target.dataset.runId || "");
      }
      if (target && target.dataset && target.dataset.action === "export-cleanup-preview") {
        previewQuantExportCleanup(target.dataset.runId || "");
      }
      if (target && target.dataset && target.dataset.action === "export-cleanup-apply") {
        applyQuantExportCleanup(target.dataset.runId || "", target.dataset.keepLast || "");
      }
      if (target && target.dataset && target.dataset.action === "verify-export") {
        verifyQuantExport(target.dataset.runId || "", target.dataset.manifestPath || "");
      }
    });
  }
  if (els.portfolioSyncBacktest) {
    els.portfolioSyncBacktest.addEventListener("click", syncPortfolioFromBacktest);
  }
  if (els.portfolioOptimize) els.portfolioOptimize.addEventListener("click", runPortfolioOptimize);
  if (els.historyToggleBtn) {
    els.historyToggleBtn.addEventListener("click", () => {
      state.historyExpanded = !state.historyExpanded;
      renderHistory();
    });
  }
  els.clearHistoryBtn.addEventListener("click", () => {
    alert("서버 기반 히스토리는 디스크에 영속 저장됩니다.\n삭제가 필요하면 data/outputs/runs/ 폴더와 data/runs.db 파일을 직접 정리하세요.");
  });

  els.evidenceSearch.addEventListener("input", applyEvidenceFilter);

  if (els.preflightPill) {
    els.preflightPill.addEventListener("click", () => {
      if (els.preflightPanel.classList.contains("hidden")) openPreflightPanel();
      else closePreflightPanel();
    });
  }
  if (els.preflightClose) {
    els.preflightClose.addEventListener("click", closePreflightPanel);
  }
  if (els.preflightRefresh) {
    els.preflightRefresh.addEventListener("click", async () => {
      els.preflightLabel.textContent = "preflight…";
      els.preflightPill.classList.remove("ok", "warn", "err");
      const r = await loadPreflight(true);
      if (r) renderPreflightPanel(r);
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !els.preflightPanel.classList.contains("hidden")) {
      closePreflightPanel();
    }
  });

  if (els.qdrantAdminBtn) {
    els.qdrantAdminBtn.addEventListener("click", () => {
      if (els.qdrantPanel.classList.contains("hidden")) openQdrantPanel();
      else closeQdrantPanel();
    });
  }
  if (els.qdrantClose) els.qdrantClose.addEventListener("click", closeQdrantPanel);
  if (els.qdrantRefresh) els.qdrantRefresh.addEventListener("click", loadQdrantInfo);
  if (els.qdrantPurgeDryRun) els.qdrantPurgeDryRun.addEventListener("click", () => runQdrantPurge(true));
  if (els.qdrantPurgeRun) els.qdrantPurgeRun.addEventListener("click", () => runQdrantPurge(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.qdrantPanel && !els.qdrantPanel.classList.contains("hidden")) {
      closeQdrantPanel();
    }
  });

  if (els.qualityDashBtn) {
    els.qualityDashBtn.addEventListener("click", () => {
      if (els.qualityPanel.classList.contains("hidden")) openQualityPanel();
      else closeQualityPanel();
    });
  }
  if (els.qualityClose) els.qualityClose.addEventListener("click", closeQualityPanel);
  if (els.qualityRefresh) els.qualityRefresh.addEventListener("click", loadQualityDashboard);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.qualityPanel && !els.qualityPanel.classList.contains("hidden")) {
      closeQualityPanel();
    }
    if (e.key === "Escape" && els.symbolPickerModal && !els.symbolPickerModal.classList.contains("hidden")) {
      closeSymbolPicker();
    }
  });
}

// ---------- Init ----------
(async function init() {
  normalizeStaticLabels();
  await loadConfig();
  bindTabs();
  bindDownloads();
  bindInputs();
  restoreForm();
  renderBacktestUniverseChips();
  populateBacktestStrategyRegistry();
  renderHistory();
  renderWatchlist();
  initializeTradingViewDashboard(false);
  loadDashboardEquityHeatmap(false);
  loadDashboardMarket(false);
  loadDataHealth(false);
  loadDashboardNews(false);
  if (els.watchlistAddBtn) {
    els.watchlistAddBtn.addEventListener("click", watchlistAddFromForm);
  }
  // Poll watchlist every 30s so scheduled runs and last_run_at timestamps stay fresh.
  state.watchlistTimer = setInterval(renderWatchlist, 30000);
  checkHealth();
  loadRunbook();
  loadPreflight(false);
  state.preflightTimer = setInterval(() => loadPreflight(false), 60000);
})();
