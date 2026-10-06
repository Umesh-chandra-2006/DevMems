# Key verification, 2026-10-07 (live, 29 requests; key NAMES and HTTP statuses only, no value anywhere)

Method: `devmem/router/verify_new_keys.py` (one minimal call per key; Gemini keys also one embedding request). Raw statuses appended to `docs/phase5_step2_artifacts/key_verification.json`.

| Provider | New names tried | Result | Added to config |
|---|---|---|---|
| Groq (`openai/gpt-oss-20b`, max_tokens 5) | GROQ_KEY_10 to GROQ_KEY_19 (10) | 9 return 200 (10 to 18); GROQ_KEY_19 is a name in `.env` with NO value, so no call was made | GROQ_KEY_10 to 18 in `providers.yaml` (Groq now 18 keys) |
| Gemini chat (`gemini-3.1-flash-lite`, maxOutputTokens 5) | GEMINI_KEY_8 to GEMINI_KEY_17 (10) | 9 return 200 (8, 10 to 17); GEMINI_KEY_9 returns 403 | GEMINI_KEY_8, 10 to 17 in `providers.yaml` |
| Gemini embeddings (`gemini-embedding-001`, one embedContent) | same 10 | 9 return 200 (8, 10 to 17); GEMINI_KEY_9 returns 403 | same keys in `embeddings.yaml` |

Totals: Groq calls 9 (+0 for the empty name), Gemini calls 20 (10 chat + 10 embedding), 29 requests. GEMINI_KEY_9 stays out (403, reported, not retried).

Pinned-model summary: **chat-capable with `gemini-3.1-flash-lite`**: GEMINI_KEY_1, 2, 4, 5, 6 (verified earlier) and 8, 10, 11, 12, 13, 14, 15, 16, 17 (verified today) = 14 keys. **Embedding-capable with `gemini-embedding-001`**: GEMINI_KEY_1, 3, 4, 5, 6 (earlier) and 8, 10 to 17 = 14 keys. GEMINI_KEY_3 was verified for embeddings only; GEMINI_KEY_7 returned 403 earlier; neither is in the chat list. Groq keys are not used for the Phase 7 or Phase 9 runs (both arms use the pinned Gemini model); Groq stays available for tests and the presentation's live segment.
