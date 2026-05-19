from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SymbolIdentity:
    ticker: str
    display_name: str
    aliases: tuple[str, ...] = ()
    market: str = ""
    asset_class: str = ""


_APP_JS = Path(__file__).resolve().parents[2] / "app" / "web" / "app.js"

_SPECIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "AAPL": ("\uc560\ud50c", "apple"),
    "MSFT": ("\ub9c8\uc774\ud06c\ub85c\uc18c\ud504\ud2b8", "microsoft"),
    "NVDA": ("\uc5d4\ube44\ub514\uc544", "nvidia"),
    "TSLA": ("\ud14c\uc2ac\ub77c", "tesla"),
    "GOOGL": ("\uc54c\ud30c\ubcb3", "\uad6c\uae00", "alphabet", "google"),
    "GOOG": ("google class c",),
    "AMZN": ("\uc544\ub9c8\uc874", "amazon"),
    "META": ("\uba54\ud0c0", "meta platforms", "facebook"),
    "AVGO": ("\ube0c\ub85c\ub4dc\ucef4", "broadcom"),
    "ORCL": ("\uc624\ub77c\ud074", "oracle"),
    "PLTR": ("\ud314\ub780\ud2f0\uc5b4", "palantir"),
    "NFLX": ("\ub137\ud50c\ub9ad\uc2a4", "netflix"),
    "AMD": ("amd", "advanced micro devices"),
    "INTC": ("\uc778\ud154", "intel"),
    "IBM": ("ibm", "international business machines"),
    "COST": ("\ucf54\uc2a4\ud2b8\ucf54", "costco"),
    "WMT": ("\uc6d4\ub9c8\ud2b8", "walmart"),
    "V": ("\ube44\uc790", "visa"),
    "JPM": ("jp\ubaa8\uac74", "jp morgan", "jpmorgan", "jpmorgan chase"),
    "BRK-B": ("\ubc84\ud06c\uc154", "berkshire", "berkshire hathaway"),
    "LLY": ("\uc77c\ub77c\uc774\ub9b4\ub9ac", "\ub9b4\ub9ac", "eli lilly"),
    "005930.KS": (
        "\uc0bc\uc131\uc804\uc790",
        "\uc0bc\uc804",
        "samsung electronics",
        "samsung electronic",
        "samsung elec",
    ),
    "000660.KS": (
        "sk\ud558\uc774\ub2c9\uc2a4",
        "\ud558\uc774\ub2c9\uc2a4",
        "sk hynix",
        "hynix",
    ),
    "035420.KS": ("naver", "\ub124\uc774\ubc84"),
    "035720.KS": ("\uce74\uce74\uc624", "kakao"),
    "005380.KS": ("\ud604\ub300\ucc28", "hyundai motor", "hyundai motors"),
    "000270.KS": ("\uae30\uc544", "kia"),
    "005490.KS": ("posco\ud640\ub529\uc2a4", "\ud3ec\uc2a4\ucf54\ud640\ub529\uc2a4", "posco holdings"),
    "006400.KS": ("\uc0bc\uc131sdi", "samsung sdi"),
    "051910.KS": ("lg\ud654\ud559", "lg chem"),
    "068270.KS": ("\uc140\ud2b8\ub9ac\uc628", "celltrion"),
    "247540.KQ": ("\uc5d0\ucf54\ud504\ub85c\ube44\uc5e0", "ecopro bm", "ecoprobiem"),
    "114800.KS": ("\ucf54\uc2a4\ud53c \uc778\ubc84\uc2a4", "kodex \uc778\ubc84\uc2a4", "kodex inverse", "kospi inverse"),
    "252670.KS": ("\uace1\ubc84\uc2a4", "\ucf54\uc2a4\ud53c \uace1\ubc84\uc2a4", "kodex 200\uc120\ubb3c\uc778\ubc84\uc2a42x", "kospi inverse 2x"),
    "251340.KS": ("\ucf54\uc2a4\ub2e5 \uc778\ubc84\uc2a4", "kodex \ucf54\uc2a4\ub2e5150\uc120\ubb3c\uc778\ubc84\uc2a4", "kosdaq inverse"),
    "BTC-USD": ("\ube44\ud2b8\ucf54\uc778", "bitcoin", "btc"),
    "ETH-USD": ("\uc774\ub354\ub9ac\uc6c0", "ethereum", "eth"),
}

_CORPORATE_SUFFIX_RE = re.compile(
    r"(?i)(?:,?\s+(?:incorporated|inc\.?|corporation|corp\.?|company|co\.?|limited|ltd\.?|plc|n\.v\.|s\.a\.|class\s+[a-z]|common\s+stock))+$"
)
_LEADING_ARTICLE_RE = re.compile(r"(?i)^the\s+")
_ALIAS_STOPWORDS = {
    "the",
    "company",
    "corporation",
    "inc",
    "inc.",
    "class a",
    "class b",
    "common stock",
}


def _repo_app_js() -> str:
    try:
        return _APP_JS.read_text(encoding="utf-8")
    except OSError:
        return ""


def _template_block(source: str, const_name: str) -> str:
    pattern = re.compile(
        rf"const\s+{re.escape(const_name)}\s*=\s*Object\.fromEntries\(symbolNameList\(`(?P<body>.*?)`\)\);",
        re.DOTALL,
    )
    match = pattern.search(source)
    return match.group("body") if match else ""


def _symbol_list_block(source: str, const_name: str) -> list[str]:
    pattern = re.compile(rf"const\s+{re.escape(const_name)}\s*=\s*symbolList\(`(?P<body>.*?)`\);", re.DOTALL)
    match = pattern.search(source)
    if not match:
        return []
    return [item.strip().upper() for item in re.split(r"\s+", match.group("body").strip()) if item.strip()]


def _array_symbols(source: str, const_name: str) -> list[str]:
    pattern = re.compile(rf"const\s+{re.escape(const_name)}\s*=\s*\[(?P<body>.*?)\];", re.DOTALL)
    match = pattern.search(source)
    if not match:
        return []
    return [item.upper() for item in re.findall(r'"([^"]+)"', match.group("body"))]


def _symbol_names(source: str, const_name: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for raw_line in _template_block(source, const_name).splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        symbol, name = line.split("|", 1)
        symbol = symbol.strip().upper()
        name = " ".join(name.strip().split())
        if symbol and name:
            names[symbol] = name
    return names


def _symbol_overrides(source: str) -> dict[str, str]:
    pattern = re.compile(r"const\s+SYMBOL_NAME_OVERRIDES\s*=\s*\{(?P<body>.*?)\};", re.DOTALL)
    match = pattern.search(source)
    if not match:
        return {}
    overrides: dict[str, str] = {}
    line_re = re.compile(r'\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>[A-Z0-9.-]+))\s*:\s*"(?P<name>[^"]+)"\s*,?')
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        found = line_re.match(line)
        if not found:
            continue
        symbol = (found.group("quoted") or found.group("bare") or "").upper()
        name = " ".join((found.group("name") or "").split())
        if symbol and name:
            overrides[symbol] = name
    return overrides


def _clean_alias(value: str) -> str:
    return " ".join(str(value or "").replace("\u00b7", " ").split()).strip()


def _base_display_name(name: str) -> str:
    return _clean_alias(str(name or "").split("(", 1)[0])


def _safe_name_alias(alias: str) -> str:
    alias = _clean_alias(alias).strip(" ,.-")
    if not alias:
        return ""
    alias = _LEADING_ARTICLE_RE.sub("", alias).strip(" ,.-")
    alias = _CORPORATE_SUFFIX_RE.sub("", alias).strip(" ,.-")
    if alias.lower().endswith(".com"):
        without_dotcom = alias[:-4].strip(" ,.-")
        if len(without_dotcom) >= 4:
            alias = without_dotcom
    alias = _clean_alias(alias)
    if not alias or alias.casefold() in _ALIAS_STOPWORDS:
        return ""
    if not re.search(r"[\uac00-\ud7a3]", alias) and re.fullmatch(r"[A-Za-z]{1,2}", alias):
        return ""
    return alias


def _name_aliases(*names: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for name in names:
        cleaned_name = _clean_alias(name)
        base_name = _base_display_name(cleaned_name)
        safe_name = _safe_name_alias(cleaned_name)
        safe_base_name = _safe_name_alias(base_name)
        candidates = (
            cleaned_name if safe_name else "",
            safe_name,
            safe_base_name,
        )
        for candidate in candidates:
            candidate = _clean_alias(candidate)
            if not candidate:
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            aliases.append(candidate)
    return aliases


def _aliases_for(ticker: str, display_name: str, raw_name: str = "") -> tuple[str, ...]:
    aliases: list[str] = [ticker]
    if "." in ticker:
        aliases.append(ticker.split(".", 1)[0])
    aliases.extend(_name_aliases(display_name, raw_name))
    aliases.extend(_SPECIAL_ALIASES.get(ticker, ()))

    cleaned: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        alias = _clean_alias(alias)
        if not alias:
            continue
        key = alias.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(alias)
    return tuple(cleaned)


def _add_identity(
    identities: dict[str, SymbolIdentity],
    ticker: str,
    display_name: str,
    *,
    raw_name: str = "",
    market: str = "",
    asset_class: str = "",
) -> None:
    ticker = str(ticker or "").upper().strip()
    display_name = _clean_alias(display_name or ticker)
    if not ticker:
        return
    existing = identities.get(ticker)
    merged_aliases = _aliases_for(ticker, display_name, raw_name=raw_name)
    if existing is not None:
        merged_aliases = tuple(dict.fromkeys([*existing.aliases, *merged_aliases]))
        display_name = existing.display_name if existing.display_name != existing.ticker else display_name
        market = existing.market or market
        asset_class = existing.asset_class or asset_class
    identities[ticker] = SymbolIdentity(
        ticker=ticker,
        display_name=display_name,
        aliases=merged_aliases,
        market=market,
        asset_class=asset_class,
    )


@lru_cache(maxsize=1)
def symbol_identities() -> dict[str, SymbolIdentity]:
    source = _repo_app_js()
    us_names = _symbol_names(source, "US_SYMBOL_NAMES")
    etf_names = _symbol_names(source, "ETF_SYMBOL_NAMES")
    kr_names = _symbol_names(source, "KOREAN_SYMBOL_NAMES")
    kr_etf_names = _symbol_names(source, "KOREAN_ETF_NAMES")
    overrides = _symbol_overrides(source)

    identities: dict[str, SymbolIdentity] = {}
    for symbol in _symbol_list_block(source, "US_LARGE_CAP_SYMBOLS"):
        _add_identity(
            identities,
            symbol,
            overrides.get(symbol) or us_names.get(symbol) or symbol,
            raw_name=us_names.get(symbol, ""),
            market="US",
            asset_class="stock",
        )
    for symbol in _symbol_list_block(source, "ETF_CORE_SYMBOLS"):
        _add_identity(
            identities,
            symbol,
            overrides.get(symbol) or etf_names.get(symbol) or symbol,
            raw_name=etf_names.get(symbol, ""),
            market="US ETF",
            asset_class="etf",
        )
    for code in _symbol_list_block(source, "KOSPI200_SYMBOLS"):
        ticker = f"{code}.KS"
        name = kr_names.get(code) or code
        _add_identity(
            identities,
            ticker,
            overrides.get(ticker) or f"{name} ({code} KOSPI 200)",
            raw_name=name,
            market="KRX",
            asset_class="stock",
        )
    for code in _symbol_list_block(source, "KOSDAQ100_SYMBOLS"):
        ticker = f"{code}.KQ"
        name = kr_names.get(code) or code
        _add_identity(
            identities,
            ticker,
            overrides.get(ticker) or f"{name} ({code} KOSDAQ 100)",
            raw_name=name,
            market="KRX",
            asset_class="stock",
        )
    for code in _symbol_list_block(source, "KOREAN_ETF_SYMBOLS"):
        ticker = f"{code}.KS"
        name = kr_etf_names.get(code) or code
        _add_identity(
            identities,
            ticker,
            overrides.get(ticker) or f"{name} ({code} KRX ETF)",
            raw_name=name,
            market="KRX",
            asset_class="etf",
        )
    for symbol in _array_symbols(source, "CRYPTO_SYMBOLS"):
        _add_identity(
            identities,
            symbol,
            overrides.get(symbol) or symbol,
            market="GLOBAL",
            asset_class="crypto",
        )

    for ticker, aliases in _SPECIAL_ALIASES.items():
        existing = identities.get(ticker)
        display = existing.display_name if existing else ticker
        _add_identity(identities, ticker, display, raw_name=aliases[0])
    return identities


def known_symbol_tickers() -> set[str]:
    return set(symbol_identities())


def symbol_display_name(ticker: str | None) -> str:
    clean = str(ticker or "").upper().strip()
    identity = symbol_identities().get(clean)
    return identity.display_name if identity else clean


def _is_hangul_or_numeric_alias(alias: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", alias) or re.fullmatch(r"\d{6}(?:\.(?:KS|KQ))?", alias, re.IGNORECASE))


def _alias_position(text: str, alias: str) -> int:
    alias = _clean_alias(alias)
    if not alias:
        return -1
    if re.fullmatch(r"\d{6}(?:\.(?:KS|KQ))?", alias, re.IGNORECASE):
        pattern = re.compile(rf"(?<!\d){re.escape(alias)}(?!\d)", re.IGNORECASE)
        match = pattern.search(text)
        return match.start() if match else -1
    if re.search(r"[\uac00-\ud7a3]", alias):
        return text.casefold().find(alias.casefold())
    if len(alias) < 4 and not re.fullmatch(r"[A-Z0-9.-]{1,8}", alias, re.IGNORECASE):
        return -1
    flags = 0 if re.fullmatch(r"[A-Z]{1,3}", alias) else re.IGNORECASE
    pattern = re.compile(rf"(?<![A-Za-z0-9.$=-]){re.escape(alias)}(?![A-Za-z0-9])", flags)
    match = pattern.search(text)
    return match.start() if match else -1


def iter_symbol_alias_matches(text: str | None, *, limit: int = 8) -> list[SymbolIdentity]:
    haystack = str(text or "")
    if not haystack.strip():
        return []

    matches: list[tuple[int, int, SymbolIdentity]] = []
    for identity in symbol_identities().values():
        best_pos = -1
        best_len = 0
        for alias in identity.aliases:
            pos = _alias_position(haystack, alias)
            if pos < 0:
                continue
            alias_len = len(alias)
            if best_pos < 0 or pos < best_pos or (pos == best_pos and alias_len > best_len):
                best_pos = pos
                best_len = alias_len
        if best_pos >= 0:
            matches.append((best_pos, -best_len, identity))

    matches.sort(key=lambda item: (item[0], item[1], item[2].ticker))
    out: list[SymbolIdentity] = []
    seen: set[str] = set()
    for _, _, identity in matches:
        if identity.ticker in seen:
            continue
        seen.add(identity.ticker)
        out.append(identity)
        if len(out) >= limit:
            break
    return out


def resolve_symbol_aliases(text: str | None, *, limit: int = 8) -> list[str]:
    return [identity.ticker for identity in iter_symbol_alias_matches(text, limit=limit)]


__all__ = [
    "SymbolIdentity",
    "iter_symbol_alias_matches",
    "known_symbol_tickers",
    "resolve_symbol_aliases",
    "symbol_display_name",
    "symbol_identities",
]
