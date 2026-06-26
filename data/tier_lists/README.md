# Overframe tier lists

Static tier data for the ranking agent, merged into a single file.

## File

| File | Content |
|------|---------|
| `overframe.json` | All categories: warframes, primary, secondary, melee, archwing, companions |

Format:

```json
{
  "updated_at": "...",
  "categories": {
    "warframes": { "wisp": { "tier": "S", "name": "Wisp" } }
  }
}
```

To refresh tiers, edit `overframe.json` directly or regenerate from source PDFs outside this repo.
