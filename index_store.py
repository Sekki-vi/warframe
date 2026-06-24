"""Embed WFI RAG documents and upsert into Pinecone."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from openai import OpenAI
from pinecone import Pinecone

from config import WFI_RAG_DOCS_JSONL
from pinecone_config import get_config


def pinecone_id(doc_id: str) -> str:
    """Pinecone requires ASCII vector IDs."""
    if doc_id.isascii():
        return doc_id
    digest = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()[:32]
    return f"id_{digest}"


def _build_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "doc_id": doc.get("id") or "",
        "text": doc.get("metadata_text") or "",
        "slug": doc.get("slug") or "",
        "name": doc.get("name") or "",
        "unique_name": doc.get("unique_name") or "",
        "category": doc.get("category") or "",
        "type": doc.get("type") or "",
        "equipment_class": doc.get("equipment_class") or "",
        "weapon_subtype": doc.get("weapon_subtype") or "",
        "taxonomy": doc.get("taxonomy") or "",
        "image_url": doc.get("image_url") or "",
        "wiki_link": doc.get("wiki_link") or "",
        "tier": doc.get("tier") or "",
        "item_variant": doc.get("item_variant") or "",
        "description": doc.get("description") or "",
        "aliases": doc.get("aliases") or "",
        "rarity": doc.get("rarity") or "",
        "polarity": doc.get("polarity") or "",
    }
    wfm_slug = doc.get("wfm_slug")
    if wfm_slug:
        meta["wfm_slug"] = wfm_slug
    return meta


def embed_batch(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in resp.data]


def index_documents(docs: list[dict[str, Any]] | None = None, *, delete_stale: bool = True) -> None:
    """Embed and upsert WFI RAG documents into Pinecone."""
    cfg = get_config()

    if docs is None:
        docs = []
        with WFI_RAG_DOCS_JSONL.open(encoding="utf-8") as f:
            for line in f:
                docs.append(json.loads(line))

    if not docs:
        print("No documents to index.")
        return

    new_ids = {pinecone_id(doc["id"]) for doc in docs}

    pc = Pinecone(api_key=cfg["pinecone_key"])
    desc = pc.describe_index(cfg["index_name"])
    if desc.dimension != cfg["dimensions"]:
        raise SystemExit(
            f"Index '{cfg['index_name']}' has dimension {desc.dimension}, but "
            f"{cfg['embed_model']} produces {cfg['dimensions']}-dim vectors."
        )

    index = pc.Index(cfg["index_name"])

    if delete_stale:
        stats = index.describe_index_stats()
        ns_stats = stats.get("namespaces", {}).get(cfg["namespace"], {})
        if ns_stats.get("vector_count", 0) > len(docs):
            print("Deleting stale vectors from namespace ...")
            index.delete(delete_all=True, namespace=cfg["namespace"])

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
        f"(namespace '{cfg['namespace']}', vectors in namespace: {ns_stats.get('vector_count', '?')}, "
        f"unique ids: {len(new_ids)})"
    )
