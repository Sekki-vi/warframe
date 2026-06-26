# Warframe Knowledge + Ranking Agents

Two library agents for a future Ordis-style manager:

| Agent | Source | Purpose |
|-------|--------|---------|
| Knowledge | Pinecone + local alias index | Non-tradable item descriptions, stats, drops |
| Ranking | `data/tier_lists/overframe.json` | Overframe tier lookup (S–D) |

Knowledge does **not** embed tier data. Ranking is a separate JSON lookup the manager will call later.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill in API keys
3. Ensure local runtime data exists (not in git):
   - `data/processed/knowledge_index.json` (required)
   - `data/processed/knowledge_corpus.jsonl` (optional archive)
   - `data/cache/` (wfi lookup, wiki drops cache, etc.)
4. Pinecone index `warframe`, namespace `warframe` must already be populated

### Pinecone

- Index: `warframe` (1536-dim, cosine)
- Namespace: `warframe`

## Usage

```python
from agents.knowledge.agent import answer, retrieve
from agents.ranking.agent import lookup_tier, enrich_response

hits, intent = retrieve("Excalibur")
print(hits[0]["name"])

result = answer("Tell me about Excalibur")
print(result["reply"])

print(lookup_tier("wisp", "warframes"))
```

## Tier data

Edit `data/tier_lists/overframe.json` or see [data/tier_lists/README.md](data/tier_lists/README.md).

## Future work

See [docs/ARCHITECTURE_FUTURE.md](docs/ARCHITECTURE_FUTURE.md) for the planned manager router and market agent.
