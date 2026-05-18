from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from core.schemas.forecast import TargetConfig, ValidationConfig


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_end: int

    def as_dict(self, dates: list[str]) -> dict:
        return {
            "fold_id": self.fold_id,
            "train_start": dates[self.train_start],
            "train_end": dates[max(self.train_start, self.train_end - 1)],
            "test_start": dates[self.test_start],
            "test_end": dates[max(self.test_start, self.test_end - 1)],
            "train_size": max(0, self.train_end - self.train_start),
            "test_size": max(0, self.test_end - self.test_start),
            "embargo_end": dates[min(len(dates) - 1, max(self.test_start, self.embargo_end - 1))],
        }


@dataclass(frozen=True)
class PurgedCombinatorialFold:
    fold_id: int
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    test_groups: tuple[int, ...]
    purge_window: int
    embargo_window: int

    def as_dict(self, dates: list[str]) -> dict:
        train = list(self.train_indices)
        test = list(self.test_indices)
        return {
            "fold_id": self.fold_id,
            "validation_method": "purged_combinatorial_cv",
            "test_groups": list(self.test_groups),
            "train_start": dates[min(train)] if train else "",
            "train_end": dates[max(train)] if train else "",
            "test_start": dates[min(test)] if test else "",
            "test_end": dates[max(test)] if test else "",
            "train_size": len(train),
            "test_size": len(test),
            "purge_window": self.purge_window,
            "embargo_window": self.embargo_window,
        }


def create_walk_forward_splits(
    dates: list[str],
    validation_config: ValidationConfig,
    target_config: TargetConfig,
) -> tuple[list[WalkForwardFold], list[str]]:
    n = len(dates)
    warnings: list[str] = []
    if n < 40:
        return [], ["insufficient_rows_for_walk_forward"]
    train_window = _window_to_bars(validation_config.train_window, fallback=756)
    test_window = _window_to_bars(validation_config.test_window, fallback=126)
    step = _window_to_bars(validation_config.step_size, fallback=21)
    purge = int(target_config.horizon) if str(validation_config.purge_window).lower() == "auto" else _window_to_bars(validation_config.purge_window, fallback=target_config.horizon)
    embargo = int(validation_config.embargo_window or 0)
    if n < train_window + purge + test_window:
        train_window = max(20, int(n * 0.55))
        test_window = max(10, int(n * 0.18))
        step = max(5, int(test_window // 2))
        warnings.append("walk_forward_windows_compacted_for_available_history")
    folds: list[WalkForwardFold] = []
    fold_id = 1
    train_start = 0
    test_start = train_window + purge
    while test_start + test_window <= n:
        train_end = max(train_start + 1, test_start - purge)
        if train_end - train_start >= 20:
            folds.append(
                WalkForwardFold(
                    fold_id=fold_id,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_start + test_window,
                    embargo_end=min(n, test_start + test_window + embargo),
                )
            )
            fold_id += 1
        if validation_config.expanding:
            test_start += step
        else:
            train_start += step
            test_start += step
    if not folds:
        split = max(20, int(n * 0.7))
        test_start = min(n - 10, split + purge)
        if test_start < n:
            folds.append(
                WalkForwardFold(
                    fold_id=1,
                    train_start=0,
                    train_end=max(1, test_start - purge),
                    test_start=test_start,
                    test_end=n,
                    embargo_end=n,
                )
            )
            warnings.append("single_walk_forward_fold_used")
    return folds, warnings


def create_purged_combinatorial_splits(
    dates: list[str],
    validation_config: ValidationConfig,
    target_config: TargetConfig,
    *,
    n_groups: int = 6,
    test_group_count: int = 2,
    max_splits: int = 12,
) -> tuple[list[PurgedCombinatorialFold], list[str]]:
    n = len(dates)
    warnings: list[str] = []
    if n < 40:
        return [], ["insufficient_rows_for_purged_combinatorial_cv"]
    n_groups = max(4, min(int(n_groups or 6), 12, n // 10))
    test_group_count = max(1, min(int(test_group_count or 2), n_groups - 1))
    purge = int(target_config.horizon) if str(validation_config.purge_window).lower() == "auto" else _window_to_bars(validation_config.purge_window, fallback=target_config.horizon)
    embargo = int(validation_config.embargo_window or 0)
    group_bounds = _contiguous_group_bounds(n, n_groups)
    folds: list[PurgedCombinatorialFold] = []
    for fold_id, combo in enumerate(combinations(range(n_groups), test_group_count), start=1):
        if len(folds) >= max_splits:
            warnings.append("purged_combinatorial_cv_splits_capped")
            break
        test_indices = sorted(idx for group in combo for idx in range(group_bounds[group][0], group_bounds[group][1]))
        excluded = set(test_indices)
        for group in combo:
            start, end = group_bounds[group]
            purge_start = max(0, start - purge)
            embargo_end = min(n, end + embargo)
            excluded.update(range(purge_start, embargo_end))
        train_indices = tuple(idx for idx in range(n) if idx not in excluded)
        if len(train_indices) < 20 or len(test_indices) < 5:
            warnings.append(f"purged_combinatorial_cv_fold_skipped:{combo}")
            continue
        folds.append(
            PurgedCombinatorialFold(
                fold_id=fold_id,
                train_indices=train_indices,
                test_indices=tuple(test_indices),
                test_groups=tuple(combo),
                purge_window=purge,
                embargo_window=embargo,
            )
        )
    if not folds:
        warnings.append("purged_combinatorial_cv_unavailable_after_purge_embargo")
    return folds, warnings


def _window_to_bars(value: str | int, *, fallback: int) -> int:
    if isinstance(value, int):
        return max(1, value)
    text = str(value or "").strip().lower()
    if not text:
        return fallback
    try:
        return max(1, int(text))
    except ValueError:
        pass
    number = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    try:
        amount = int(number)
    except ValueError:
        return fallback
    if unit.startswith("y"):
        return amount * 252
    if unit.startswith("m"):
        return amount * 21
    if unit.startswith("w"):
        return amount * 5
    return amount


def _contiguous_group_bounds(n: int, n_groups: int) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    for group in range(n_groups):
        start = round(group * n / n_groups)
        end = round((group + 1) * n / n_groups)
        bounds.append((start, max(start + 1, end)))
    bounds[-1] = (bounds[-1][0], n)
    return bounds
