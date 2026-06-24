#!/usr/bin/env python3
"""Build WFI knowledge documents and alias index."""
from __future__ import annotations

import argparse

from agents.knowledge.ingest import run_ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build WFI knowledge documents + alias index")
    parser.add_argument(
        "--force-wfm",
        action="store_true",
        help="Re-fetch WFM items manifest (tradable slug list + wiki links)",
    )
    args = parser.parse_args()
    docs, index = run_ingest(force_wfm=args.force_wfm)
    print(f"Documents: {len(docs)}")
    print(f"Alias index keys: name={len(index['name_to_doc'])}, taxonomy={len(index['taxonomy_to_docs'])}")


if __name__ == "__main__":
    main()
