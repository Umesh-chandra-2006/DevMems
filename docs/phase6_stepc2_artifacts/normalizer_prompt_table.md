## 1. Rendered upstream prompts in the call path (from the real template files)

| template | readable by upstream on this machine | stripped | why |
|---|---|---|---|
| persona/prompt_template/safety/anthromorphosization_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v1/action_location_object_vMar11.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v1/action_location_sector_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v1/action_object_v2.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/agent_chat_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/convo_to_thoughts_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/create_conversation_v2.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/daily_planning_v6.txt | yes | yes | daily_plan: Unicode spaces mapped (original scope) and the annotation stripped |
| persona/prompt_template/v2/decide_to_react_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/decide_to_talk_v2.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/generate_event_triple_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/generate_focal_pt_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/generate_hourly_schedule_v2.txt | yes | yes | hourly_schedule: Unicode spaces mapped (original scope) and the annotation stripped |
| persona/prompt_template/v2/generate_next_convo_line_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/generate_obj_event_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/generate_pronunciatio_v1.txt | no (cp1252) | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/get_keywords_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/insight_and_evidence_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/keyword_to_thoughts_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/memo_on_convo_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/new_decomp_schedule_v1.txt | yes | NO (veto) | decomposition prompt: its parser reads the annotation (run_gpt_prompt.py lines 374 and 381); reply returned untouched |
| persona/prompt_template/v2/planning_thought_on_convo_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/poignancy_chat_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/poignancy_event_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/poignancy_thought_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/summarize_chat_ideas_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/summarize_chat_relationship_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/summarize_conversation_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/summarize_ideas_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v2/task_decomp_v3.txt | yes | NO (veto) | decomposition prompt: its parser reads the annotation (run_gpt_prompt.py lines 374 and 381); reply returned untouched |
| persona/prompt_template/v2/wake_up_hour_v1.txt | yes | yes | wake_up_hour: Unicode spaces mapped (original scope) and the annotation stripped |
| persona/prompt_template/v2/whisper_inner_thought_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/action_location_sector_v2.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/agent_chat_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/generate_event_triple_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/generate_focal_pt_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/generate_hourly_schedule_v2.txt | yes | yes | hourly_schedule: Unicode spaces mapped (original scope) and the annotation stripped |
| persona/prompt_template/v3_ChatGPT/generate_next_convo_line_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/generate_obj_event_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/generate_pronunciatio_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/iterative_convo_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/memo_on_convo_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/poignancy_chat_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/poignancy_event_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/poignancy_thought_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/summarize_chat_ideas_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/summarize_chat_relationship_v2.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/summarize_conversation_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| persona/prompt_template/v3_ChatGPT/summarize_ideas_v1.txt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| devmem staged importance scoring prompt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |
| devmem consolidation summary prompt | yes | yes | call path, not decomposition: the annotation is stripped, nothing else is changed |

## 2. Saved live Step C replies replayed (live prompt, real upstream function and validator, real router wiring)

| prompt type | live replies | stripped | prompt equals live prompt | before: validator results, attempts, result | after: validator results, attempts, result |
|---|---|---|---|---|---|
| wake_up_hour | 1 | yes | True | [True], 1, '6'  | [True], 1, '6'  |
| daily_plan | 1 | yes | True | [True], 1, "['wake up and complete the morning routi"  | [True], 1, "['wake up and complete the morning routi"  |
| hourly_schedule | 1 | yes | True | [True], 1, 'waking up and completing her morning rou'  | [True], 1, 'waking up and completing her morning rou'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'preparing for work and commuting to Hobb'  | [True], 1, 'preparing for work and commuting to Hobb'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'opening Hobbs Cafe (duration in minutes:'  | [True], 1, 'opening Hobbs Cafe'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing cafe oper'  | [True], 1, 'serving customers and managing cafe oper'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing cafe oper'  | [True], 1, 'serving customers and managing cafe oper'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing cafe oper'  | [True], 1, 'serving customers and managing cafe oper'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing cafe oper'  | [True], 1, 'serving customers and managing cafe oper'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'taking a lunch break (duration in minute'  | [True], 1, 'taking a lunch break'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'managing the cafe and gathering party su'  | [True], 1, 'managing the cafe and gathering party su'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'gathering party supplies and managing th'  | [True], 1, 'gathering party supplies and managing th'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'gathering party supplies and managing th'  | [True], 1, 'gathering party supplies and managing th'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and gathering party su'  | [True], 1, 'serving customers and gathering party su'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing party sup'  | [True], 1, 'serving customers and managing party sup'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'serving customers and managing party sup'  | [True], 1, 'serving customers and managing party sup'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'closing Hobbs Cafe and cleaning up after'  | [True], 1, 'closing Hobbs Cafe and cleaning up after'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'preparing party decorations for the Vale'  | [True], 1, 'preparing party decorations for the Vale'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'finishing up the party decorations for t'  | [True], 1, 'finishing up the party decorations for t'  |
| hourly_schedule | 1 | yes | True | [True], 1, 'winding down for the night and going to '  | [True], 1, 'winding down for the night and going to '  |
| task_decomp | 1 | NO (veto) | n/a | annotation kept | annotation kept |
| action_sector | 5 | yes | True | [False, False, False, False, False], 5, "Isabella Rodriguez's apartment"  | [True], 1, "Isabella Rodriguez's apartment"  |
| action_arena | 5 | yes | True | [False, False, False, False, False], 5, 'kitchen'  | [True], 1, 'main room'  |

## 3. Synthetic validator checks (label: synthetic)

| function | reply form | clean result | annotated, flag off | annotated, flag on | on equals clean |
|---|---|---|---|---|---|
| action game object | plain | 'bed' | 'closet'  | 'bed' | True |
| event triple | plain | "('Isabella Rodriguez', 'wake u" | "('Isabella Rodriguez', 'wake u"  | "('Isabella Rodriguez', 'wake u" | True |
| act obj event triple | plain | "('bed', 'is', 'being used')" | "('bed', 'is', 'being used')"  | "('bed', 'is', 'being used')" | True |
| pronunciatio | json | '😴' | '😴 ('  | '😴' | True |
| act obj desc | json | 'being used by Isabella' | 'being used by Isabella (durati'  | 'being used by Isabella' | True |
| poignancy event | json | '3' | 'None' TypeError: 'NoneType' object is not subscriptable | '3' | True |
| poignancy chat | json | '3' | 'None' TypeError: 'NoneType' object is not subscriptable | '3' | True |
