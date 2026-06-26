"""Walk-forward backtesting for the Warframe forecasting agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .forecast_core import downsample, forecast
from .warframe_forecast_agent import WarframeMarketError, _load_item_series


@dataclass
class FoldResult:
    origin_index: int
    cutoff_datetime: str | None
    train_last: float
    actual: list[float]
    predicted_mean: list[float]
    lo80: list[float]
    hi80: list[float]
    lo95: list[float]
    hi95: list[float]
    mae: float
    rmse: float
    mape: float
    direction_correct: bool
    coverage_80: float
    coverage_95: float


@dataclass
class BacktestResult:
    item_name: str
    url_name: str
    timeframe: str
    price_field: str
    horizon: int
    points: int
    origin_stride: int
    folds: list[FoldResult] = field(default_factory=list)

    @property
    def n_folds(self) -> int:
        return len(self.folds)

    def summary(self) -> dict[str, float]:
        if not self.folds:
            return {}
        return {
            "mae": float(np.mean([fold.mae for fold in self.folds])),
            "rmse": float(np.mean([fold.rmse for fold in self.folds])),
            "mape": float(np.mean([fold.mape for fold in self.folds])),
            "direction_accuracy": float(np.mean([fold.direction_correct for fold in self.folds])),
            "coverage_80": float(np.mean([fold.coverage_80 for fold in self.folds])),
            "coverage_95": float(np.mean([fold.coverage_95 for fold in self.folds])),
        }

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary()
        return {
            "item_name": self.item_name,
            "url_name": self.url_name,
            "timeframe": self.timeframe,
            "price_field": self.price_field,
            "horizon": self.horizon,
            "points": self.points,
            "origin_stride": self.origin_stride,
            "n_folds": self.n_folds,
            "summary": summary,
            "folds": [
                {
                    "origin_index": fold.origin_index,
                    "cutoff_datetime": fold.cutoff_datetime,
                    "train_last": fold.train_last,
                    "mae": fold.mae,
                    "rmse": fold.rmse,
                    "mape": fold.mape,
                    "direction_correct": fold.direction_correct,
                    "coverage_80": fold.coverage_80,
                    "coverage_95": fold.coverage_95,
                    "actual": fold.actual,
                    "predicted_mean": fold.predicted_mean,
                }
                for fold in self.folds
            ],
        }


def _pct_error(actual: float, predicted: float) -> float:
    if actual == 0:
        return 0.0
    return abs(actual - predicted) / abs(actual) * 100.0


def _score_fold(
    train: np.ndarray,
    actual: np.ndarray,
    fc: dict[str, np.ndarray],
) -> tuple[float, float, float, bool, float, float]:
    predicted = fc["mean"]
    errors = actual - predicted
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    mape = float(np.mean([_pct_error(a, p) for a, p in zip(actual, predicted, strict=True)]))

    train_last = float(train[-1])
    actual_end = float(actual[-1])
    predicted_end = float(predicted[-1])
    direction_correct = (actual_end - train_last) * (predicted_end - train_last) >= 0

    in_80 = (actual >= fc["lo80"]) & (actual <= fc["hi80"])
    in_95 = (actual >= fc["lo95"]) & (actual <= fc["hi95"])
    coverage_80 = float(np.mean(in_80))
    coverage_95 = float(np.mean(in_95))
    return mae, rmse, mape, direction_correct, coverage_80, coverage_95


def walk_forward_backtest(
    item_query: str,
    *,
    timeframe: str = "90days",
    price_field: str = "median",
    points: int = 60,
    horizon: int = 12,
    paths: int = 5000,
    recent_frac: float = 0.35,
    seed: int = 42,
    origin_stride: int = 1,
    min_train_points: int | None = None,
) -> BacktestResult:
    """Walk-forward backtest for one item."""
    loaded = _load_item_series(
        item_query,
        timeframe=timeframe,
        price_field=price_field,
        points=10**9,
    )
    raw_series = loaded["raw_series"]
    market_points = loaded["market_points"]
    ds_full = downsample(raw_series, points)

    min_train = min_train_points or max(15, int(points * 0.4))
    if len(ds_full) < min_train + horizon:
        raise WarframeMarketError(
            f"Not enough history for backtesting {loaded['item']['item_name']}. "
            f"Need at least {min_train + horizon} downsampled points, got {len(ds_full)}."
        )

    result = BacktestResult(
        item_name=loaded["item"]["item_name"],
        url_name=loaded["item"]["url_name"],
        timeframe=timeframe,
        price_field=price_field,
        horizon=horizon,
        points=points,
        origin_stride=origin_stride,
    )

    raw_to_datetime = {
        index: market_points[index]["datetime"]
        for index in range(len(market_points))
    }

    for origin in range(min_train, len(ds_full) - horizon + 1, origin_stride):
        train = ds_full[:origin]
        actual = ds_full[origin : origin + horizon]
        fc = forecast(train, horizon, paths, recent_frac, seed)

        mae, rmse, mape, direction_correct, coverage_80, coverage_95 = _score_fold(
            train, actual, fc
        )

        raw_origin = min(int(round(origin / max(len(ds_full) - 1, 1) * (len(raw_series) - 1))), len(raw_series) - 1)
        result.folds.append(
            FoldResult(
                origin_index=origin,
                cutoff_datetime=raw_to_datetime.get(raw_origin),
                train_last=float(train[-1]),
                actual=actual.tolist(),
                predicted_mean=fc["mean"].tolist(),
                lo80=fc["lo80"].tolist(),
                hi80=fc["hi80"].tolist(),
                lo95=fc["lo95"].tolist(),
                hi95=fc["hi95"].tolist(),
                mae=mae,
                rmse=rmse,
                mape=mape,
                direction_correct=direction_correct,
                coverage_80=coverage_80,
                coverage_95=coverage_95,
            )
        )

    if not result.folds:
        raise WarframeMarketError(
            f"No backtest folds generated for {loaded['item']['item_name']}. "
            "Try a longer timeframe or smaller horizon/min_train_points."
        )

    return result
