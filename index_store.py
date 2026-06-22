"""Embed RAG documents and upsert into Pinecone."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from openai import OpenAI
from pinecone import Pinecone

from config import RAG_DOCS_JSONL
from pinecone_config import get_config


def pinecone_id(doc_id: str) -> str:
    """Pinecone requires ASCII vector IDs."""
    if doc_id.isascii():
        return doc_id
    digest = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()[:32]
    return f"id_{digest}"


def _build_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    market = doc.get("market") or {}
    wfm = doc.get("wfm") or {}
    wfi = doc.get("wfi") or {}
    sell = market.get("sell") or {}
    buy = market.get("buy") or {}

    meta: dict[str, Any] = {
        "doc_id": doc.get("id") or "",
        "text": doc.get("text_for_embedding") or "",
        "slug": doc.get("slug") or "",
        "rank": doc["rank"] if doc.get("rank") is not None else -1,
        "subtype": doc.get("subtype") or "",
        "item_name": market.get("item_name") or "",
        "is_prime_part": bool(market.get("is_prime_part")),
        "price_snapshot_date": market.get("price_snapshot_date") or "",
        "image_url": doc.get("image_url") or "",
        "wiki_link": wfm.get("wikiLink") or "",
        "category": wfi.get("category") or "",
    }
    if sell:
        meta["sell_median"] = float(sell.get("platinum_median", 0))
        meta["sell_count"] = int(sell.get("count", 0))
    if buy:
        meta["buy_median"] = float(buy.get("platinum_median", 0))
        meta["buy_count"] = int(buy.get("count", 0))
    return meta


def embed_batch(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def index_documents(docs: list[dict[str, Any]] | None = None) -> None:
    """Embed and upsert RAG documents into Pinecone."""
    cfg = get_config()

    if docs is None:
        docs = []
        with RAG_DOCS_JSONL.open(encoding="utf-8") as f:
            for line in f:
                docs.append(json.loads(line))

    if not docs:
        print("No documents to index.")
        return

    pc = Pinecone(api_key=cfg["pinecone_key"])
    desc = pc.describe_index(cfg["index_name"])
    if desc.dimension != cfg["dimensions"]:
        raise SystemExit(
            f"Index '{cfg['index_name']}' has dimension {desc.dimension}, but "
            f"{cfg['embed_model']} produces {cfg['dimensions']}-dim vectors."
        )

    index = pc.Index(cfg["index_name"])
    client = OpenAI(api_key=cfg["openai_key"])
    batch_size = cfg["batch_size"]
    total = len(docs)

    for start in range(0, total, batch_size):
        batch = docs[start : start + batch_size]
        texts = [d["text_for_embedding"] for d in batch]
        embeddings = embed_batch(client, cfg["embed_model"], texts)
        vectors = [
            {
                "id": pinecone_id(doc["id"]),
                "values": emb,
                "metadata": _build_metadata(doc),
            }
            for doc, emb in zip(batch, embeddings)
        ]
        index.upsert(vectors=vectors, namespace=cfg["namespace"])
        print(f"  upserted {min(start + batch_size, total)}/{total}", flush=True)

    stats = index.describe_index_stats()
    ns_stats = stats.get("namespaces", {}).get(cfg["namespace"], {})
    print(
        f"Indexed {total} documents into Pinecone index '{cfg['index_name']}' "
        f"(namespace '{cfg['namespace']}', vectors in namespace: {ns_stats.get('vector_count', '?')})"
    )
