from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SignalRow:
    date: str
    ticker: str
    factor_values: dict[str, float | None] = field(default_factory=dict)
    research_score: float | None = None
    final_score: float | None = None
    signal: float = 0.0
    execution_date: str | None = None
    lookahead_policy: str = "close_signal_next_bar_execution"
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.date,
            "ticker": self.ticker,
            "factor_values": dict(self.factor_values),
            "research_score": self.research_score,
            "final_score": self.final_score,
            "signal": self.signal,
            "execution_date": self.execution_date,
            "lookahead_policy": self.lookahead_policy,
            "diagnostics": list(self.diagnostics),
        }
