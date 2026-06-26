# Processed knowledge data

| File | Purpose |
|------|---------|
| `knowledge_index.json` | Alias/slug index for keyword lookup (required at runtime) |
| `knowledge_corpus.jsonl` | Source document archive used to build the Pinecone index |

`data/cache/` stays local (WFI lookup, wiki drops, etc.) and is not committed.
