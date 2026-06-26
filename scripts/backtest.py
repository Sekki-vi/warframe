#!/usr/bin/env python3
"""CLI for walk-forward backtesting of Warframe Market forecast items."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from agent.forecasting.backtest import walk_forward_backtest
from agent.forecasting.warframe_forecast_agent import WarframeMarketError


def _print_item_report(result) -> None:
    summary = result.summary()
    print(f"\n=== {result.item_name} ===")
    print(f"url_name:      {result.url_name}")
    print(f"timeframe:     {result.timeframe}")
    print(f"price_field:   {result.price_field}")
    print(f"folds:         {result.n_folds}")
    print(f"horizon:       {result.horizon}")
    print(f"points:        {result.points}")
    print("summary:")
    print(f"  MAE:                 {summary['mae']:.3f}")
    print(f"  RMSE:                {summary['rmse']:.3f}")
    print(f"  MAPE:                {summary['mape']:.2f}%")
    print(f"  direction accuracy:  {summary['direction_accuracy'] * 100:.1f}%")
    print(f"  80% band coverage:   {summary['coverage_80'] * 100:.1f}%")
    print(f"  95% band coverage:   {summary['coverage_95'] * 100:.1f}%")

    last_fold = result.folds[-1]
    print("latest fold:")
    print(f"  cutoff:      {last_fold.cutoff_datetime}")
    print(f"  train_last:  {last_fold.train_last:.2f}")
    print(f"  actual end:  {last_fold.actual[-1]:.2f}")
    print(f"  forecast end:{last_fold.predicted_mean[-1]:.2f}")


def _parse_items(args: argparse.Namespace) -> list[str]:
    items: list[str] = []
    if args.item:
        items.extend(args.item)
    if args.items_file:
        path = Path(args.items_file)
        items.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest for Warframe Market forecast agent."
    )
    parser.add_argument("item", nargs="*", help="Item name(s), e.g. 'Mag Prime Set'")
    parser.add_argument(
        "--items-file",
        help="Text file with one item name per line (# comments allowed)",
    )
    parser.add_argument("--timeframe", default="90days", choices=["48hours", "90days"])
    parser.add_argument(
        "--price-field",
        default="median",
        choices=["median", "avg_price", "wa_price", "closed_price", "moving_avg"],
    )
    parser.add_argument("--points", type=int, default=60)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--paths", type=int, default=5000)
    parser.add_argument("--recent-frac", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--origin-stride",
        type=int,
        default=1,
        help="Step between walk-forward origins in downsampled index space",
    )
    parser.add_argument("--json-out", help="Write full results JSON to this path")
    args = parser.parse_args(argv)

    items = _parse_items(args)
    if not items:
        parser.error("Provide at least one item name or --items-file")

    all_results = []
    failures: list[tuple[str, str]] = []

    print("Walk-forward backtest")
    print(
        f"settings: timeframe={args.timeframe}, price_field={args.price_field}, "
        f"horizon={args.horizon}, points={args.points}, origin_stride={args.origin_stride}"
    )

    for item in items:
        try:
            result = walk_forward_backtest(
                item,
                timeframe=args.timeframe,
                price_field=args.price_field,
                points=args.points,
                horizon=args.horizon,
                paths=args.paths,
                recent_frac=args.recent_frac,
                seed=args.seed,
                origin_stride=args.origin_stride,
            )
            all_results.append(result)
            _print_item_report(result)
        except (WarframeMarketError, ValueError) as exc:
            failures.append((item, str(exc)))
            print(f"\n=== {item} ===")
            print(f"FAILED: {exc}")

    if args.json_out:
        payload = {
            "settings": {
                "timeframe": args.timeframe,
                "price_field": args.price_field,
                "points": args.points,
                "horizon": args.horizon,
                "paths": args.paths,
                "recent_frac": args.recent_frac,
                "seed": args.seed,
                "origin_stride": args.origin_stride,
            },
            "results": [result.to_dict() for result in all_results],
            "failures": [{"item": item, "error": error} for item, error in failures],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote JSON report to {args.json_out}")

    if failures and not all_results:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
