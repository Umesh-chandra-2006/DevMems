| model | wake-up valid | daily plan: validator passed / usable plans / calls | hourly: valid / echo / duration-suffix / clean / calls | tokens in / out |
|---|---|---|---|---|
| openai/gpt-oss-20b | 3/3 (answers [6, 6, 6], 3 calls) | 1/2 / 0/2 / 7 | 2/2 / 2 / 0 / 0 / 5 | 9760 / 17532 |
| openai/gpt-oss-120b | 3/3 (answers [6, 6, 6], 3 calls) | 1/2 / 0/2 / 10 | 2/2 / 1 / 0 / 1 / 2 | 7760 / 18693 |
| gemini-3.1-flash-lite | 3/3 (answers [6, 6, 6], 4 calls) | 2/2 / 0/2 / 2 | 2/2 / 0 / 2 / 0 / 2 | 4436 / 3302 |

Cut off by the cap: [{'task': 'daily_plan', 'model': 'openai/gpt-oss-20b', 'repeat': 3, 'calls_used': 2}]
