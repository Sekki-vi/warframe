#!/usr/bin/env python3
"""Upsert rag_documents.jsonl into Pinecone (standalone entrypoint)."""
from __future__ import annotations

from index_store import index_documents


def main() -> None:
    index_documents()


if __name__ == "__main__":
    main()
