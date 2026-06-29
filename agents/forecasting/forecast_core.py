"""Monte Carlo forecast and chart plotting for Warframe Market prices."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


def downsample(vals: np.ndarray, n: int) -> np.ndarray:
    if len(vals) <= n:
        return vals
    idx = np.linspace(0, len(vals) - 1, n).round().astype(int)
    return vals[idx]


def forecast(
    series: np.ndarray,
    horizon: int,
    n_paths: int,
    recent_frac: float,
    seed: int,
):
    rng = np.random.default_rng(seed)
    k = max(3, int(len(series) * recent_frac))
    recent = series[-k:]
    diffs = np.diff(recent)
    drift = float(diffs.mean())
    sigma = float(diffs.std(ddof=1)) if len(diffs) > 1 else float(np.std(series))
    sigma = max(sigma, 1e-9)
    last = float(series[-1])

    steps = rng.normal(drift, sigma, size=(n_paths, horizon))
    paths = last + np.cumsum(steps, axis=1)

    mean_fc = paths.mean(axis=0)
    lo80, hi80 = np.percentile(paths, [10, 90], axis=0)
    lo95, hi95 = np.percentile(paths, [2.5, 97.5], axis=0)
    return {
        "drift": drift,
        "sigma": sigma,
        "last": last,
        "mean": mean_fc,
        "lo80": lo80,
        "hi80": hi80,
        "lo95": lo95,
        "hi95": hi95,
    }


def _parse_dates(datetimes: list[str]) -> list[datetime] | None:
    """Parse ISO datetime strings to datetime objects. Returns None if any fail."""
    parsed = []
    for s in datetimes:
        try:
            parsed.append(datetime.fromisoformat(s.replace("Z", "+00:00")))
        except Exception:
            return None
    return parsed


def make_plot(
    series,
    fc,
    unit_label,
    title,
    out_path: str | None = None,
    history_label: str = "History (extracted)",
    datetimes: list[str] | None = None,
    timeframe: str = "90days",
) -> bytes:
    n = len(series)
    h = len(fc["mean"])

    # Build x-axis: real dates if available, else sequential index
    hist_dates = _parse_dates(datetimes) if datetimes and len(datetimes) == n else None
    use_dates = hist_dates is not None

    if use_dates:
        # Infer step size from history to project forecast dates
        if n >= 2:
            avg_step = (hist_dates[-1] - hist_dates[0]) / (n - 1)
        else:
            avg_step = timedelta(days=1)
        fc_dates = [hist_dates[-1] + avg_step * i for i in range(h + 1)]
        hist_x = hist_dates
        fc_x = fc_dates
    else:
        hist_x = list(range(n))
        fc_x = list(range(n - 1, n - 1 + h + 1))

    def join(arr):
        return np.concatenate([[fc["last"]], arr])

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(hist_x, series, color="#1f3a5f", lw=2, label=history_label)
    ax.scatter([hist_x[-1]], [fc["last"]], color="#1f3a5f", s=40, zorder=5)
    ax.fill_between(fc_x, join(fc["lo95"]), join(fc["hi95"]),
                    color="#4c78a8", alpha=0.18, label="95% confidence interval")
    ax.fill_between(fc_x, join(fc["lo80"]), join(fc["hi80"]),
                    color="#4c78a8", alpha=0.32, label="80% confidence interval")
    ax.plot(fc_x, join(fc["mean"]), color="#d1495b", lw=2, ls="--",
            label="Forecast (mean path)")

    ax.axvline(hist_x[-1], color="gray", ls=":", lw=1)
    ax.set_title(title, fontsize=14, weight="bold")

    if use_dates:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)
        ax.set_xlabel("Date")
    else:
        ax.set_xlabel("Time step (index)")

    ax.set_ylabel(f"Price ({unit_label})")
    ax.legend(loc="best", framealpha=0.9)
    ax.annotate(f"{fc['mean'][-1]:.2f}p", xy=(fc_x[-1], fc["mean"][-1]),
                xytext=(8, 0), textcoords="offset points",
                color="#d1495b", weight="bold", va="center")

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    png = buf.getvalue()
    if out_path is not None:
        Path(out_path).write_bytes(png)
    return png


def make_comparison_plot(
    series_list: list[tuple[str, np.ndarray]],
    unit_label: str,
    title: str,
    *,
    metric_label: str = "price",
) -> bytes:
    if len(series_list) < 2:
        raise ValueError("Need at least two series to compare")

    colors = ["#1f3a5f", "#d1495b", "#4c78a8", "#f28b82", "#81c995", "#fbbc04"]
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (ax_hist, ax_latest) = plt.subplots(1, 2, figsize=(14, 6))

    labels: list[str] = []
    for index, (label, series) in enumerate(series_list):
        color = colors[index % len(colors)]
        x = np.arange(len(series))
        ax_hist.plot(x, series, color=color, lw=2, label=label)
        labels.append(label)
        ax_latest.bar(index, float(series[-1]), color=color)

    ax_hist.set_title(f"{metric_label.title()} history")
    ax_hist.set_xlabel("Time step (index)")
    ax_hist.set_ylabel(f"Value ({unit_label})")
    ax_hist.legend(loc="best", framealpha=0.9)

    ax_latest.set_title(f"Latest {metric_label}")
    ax_latest.set_ylabel(f"Value ({unit_label})")
    ax_latest.set_xticks(np.arange(len(labels)))
    ax_latest.set_xticklabels(labels, rotation=20, ha="right")

    fig.suptitle(title, fontsize=14, weight="bold")
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=130)
    plt.close(fig)
    return buf.getvalue()
