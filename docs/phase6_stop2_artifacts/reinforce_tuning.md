# REINFORCE_THRESHOLD tuning (Phase 6 Stop 2)

Label: live embeddings (cache first), scripted text, no LLM calls.
Model: gemini-embedding-001; dimension 3072; real embedding requests made: 1 (cap 40).

## Positives (same theme, different nights)

| pair | cosine |
|---|---|
| baking n1 vs baking n4 | 0.8923 |
| baking n1 vs baking n2 | 0.9202 |
| baking n2 vs baking n4 | 0.9432 |

## Negatives (different themes)

| pair | cosine |
|---|---|
| baking n1 vs cake_negative n3 | 0.8583 |
| baking n4 vs cake_negative n3 | 0.8526 |
| baking n2 vs cake_negative n3 | 0.8441 |
| letters n2 vs cake_negative n3 | 0.7651 |
| conflict n3 vs letters n2 | 0.7627 |
| baking n2 vs letters n2 | 0.7564 |
| baking n1 vs letters n2 | 0.7432 |
| baking n4 vs letters n2 | 0.74 |
| baking n1 vs conflict n3 | 0.7357 |
| baking n2 vs conflict n3 | 0.7331 |
| conflict n3 vs cake_negative n3 | 0.7315 |
| baking n4 vs conflict n3 | 0.7224 |

## Decision

- min positive 0.8923, max negative 0.8583, margin 0.034
- chosen REINFORCE_THRESHOLD: **0.88**
- rule applied: groups separate and max(negatives) < chosen: protocol step 2

Positives are only the three baking pairs (the fixture has one recurring theme); the negative set contains the author-chosen topically similar 'cake_negative'. The margin is a property of those choices, not a measurement of how Stage 3 summaries from a natural run will behave.
