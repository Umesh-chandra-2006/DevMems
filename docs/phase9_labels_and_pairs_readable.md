# Phase 9: the 30 hand-labelled answers and the 20 judge calibration pairs (readable copy)

Authored by the senior developer (Claude) on 2026-10-08, BEFORE any day-3 answer exists. Synthetic text, not agent output. The Owner and the PM are asked to review a sample. Source data: `docs/phase9_grader_validation_labels.json`, `docs/phase9_judge_calibration_pairs.json` (committed in `5272d10`).

## A. Grader validation set (30 answers)

For each answer the labels say whether each checklist item is truly stated (a negated or wrong mention is false). The grader's rules are in `devmem/eval/phase9/grader.py`. Result on this set: item agreement 94.7 percent (54 of 57), answer agreement 93.3 percent (28 of 30); the 3 disagreements are entries 13 and 18 and are listed at the end.

| n | question | checklist items | answer | hand labels | note |
|---|---|---|---|---|---|
| 1 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | A blue van stopped outside the cafe in the morning. | vehicle=yes, color=yes | complete and correct |
| 2 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | I remember a delivery truck, I think it was blue. | vehicle=yes, color=yes | synonym truck, hedged but stated |
| 3 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | It was a red van. | vehicle=yes, color=no | wrong color |
| 4 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | It wasn't blue, it was a white van. | vehicle=yes, color=no | negated color |
| 5 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | Something about vanilla syrup being delivered. | vehicle=no, color=no | substring trap: vanilla is not van |
| 6 | Q_I1: On day 1, what stopped outside Hobbs Cafe in the morning, and what color was it? | vehicle in van/truck; color in blue | I don't remember anything stopping outside. | vehicle=no, color=no | no recall |
| 7 | Q_I2: On day 1, what did a man ask about before leaving the cafe without ordering? | item in croissant | A man asked whether they had any croissants left, then left. | item=yes | plural form |
| 8 | Q_I2: On day 1, what did a man ask about before leaving the cafe without ordering? | item in croissant | He asked about a muffin and walked out. | item=no | wrong item |
| 9 | Q_I2: On day 1, what did a man ask about before leaving the cafe without ordering? | item in croissant | He asked about a Croissant! | item=yes | case and punctuation |
| 10 | Q_I3: On day 1, who complained about a wrong order, and what did that person receive and what had they wanted? | name in peter/hale; received in latte; wanted in tea | Peter Hale complained: he got a latte but wanted tea. | name=yes, received=yes, wanted=yes | complete and correct |
| 11 | Q_I3: On day 1, who complained about a wrong order, and what did that person receive and what had they wanted? | name in peter/hale; received in latte; wanted in tea | A customer named Peter got a latte. | name=yes, received=yes, wanted=no | partial: no wanted item |
| 12 | Q_I3: On day 1, who complained about a wrong order, and what did that person receive and what had they wanted? | name in peter/hale; received in latte; wanted in tea | Someone complained about a wrong order, I do not recall who or what. | name=no, received=no, wanted=no | no facts |
| 13 | Q_I3: On day 1, who complained about a wrong order, and what did that person receive and what had they wanted? | name in peter/hale; received in latte; wanted in tea | Hale was handed a tea although he had asked for a latte. | name=yes, received=no, wanted=no | swapped: received and wanted are reversed, both wrong |
| 14 | Q_I4: On day 2, what did a woman look at before leaving the cafe without ordering? | object in menu | A woman studied the menu and then left. | object=yes | correct |
| 15 | Q_I4: On day 2, what did a woman look at before leaving the cafe without ordering? | object in menu | She looked at the pastry display. | object=no | wrong object |
| 16 | Q_I5: On day 2, what did the notice taped on the cafe door announce, and from when? | closure in closure/close/closed; when in monday; reason in repair | A notice said the cafe would be closed from Monday for repairs. | closure=yes, when=yes, reason=yes | complete and correct |
| 17 | Q_I5: On day 2, what did the notice taped on the cafe door announce, and from when? | closure in closure/close/closed; when in monday; reason in repair | The sign on the door announced a closure but I forget when. | closure=yes, when=no, reason=no | partial |
| 18 | Q_I5: On day 2, what did the notice taped on the cafe door announce, and from when? | closure in closure/close/closed; when in monday; reason in repair | It announced that the cafe would not close on Monday. | closure=no, when=yes, reason=no | negated closure; Monday mentioned |
| 19 | Q_I6: On day 2, what happened to the wall clock over the register? | event in stopped/stop | The wall clock over the register stopped. | event=yes | correct |
| 20 | Q_I6: On day 2, what happened to the wall clock over the register? | event in stopped/stop | The clock was running fast. | event=no | wrong event |
| 21 | Q_I7: On day 3, what did a teenager look at before leaving the cafe without ordering? | object in display/case | A teenager looked at the display case before leaving. | object=yes | correct, phrase |
| 22 | Q_I7: On day 3, what did a teenager look at before leaving the cafe without ordering? | object in display/case | He looked at the case of cookies. | object=yes | the word case alone satisfies the item list; a human accepts it |
| 23 | Q_I8: On day 3, what animal came into the cafe, and where did it lie down? | animal in dog; place in table four/table 4/four | A dog came in and lay down under table four. | animal=yes, place=yes | correct |
| 24 | Q_I8: On day 3, what animal came into the cafe, and where did it lie down? | animal in dog; place in table four/table 4/four | A dog wandered in. | animal=yes, place=no | partial |
| 25 | Q_I8: On day 3, what animal came into the cafe, and where did it lie down? | animal in dog; place in table four/table 4/four | A cat came in and lay near the window. | animal=no, place=no | wrong animal and place |
| 26 | Q_I9: On day 3, what were two customers arguing about? | topic in seat/chair; place in window | Two customers argued about a seat by the window. | topic=yes, place=yes | correct |
| 27 | Q_I9: On day 3, what were two customers arguing about? | topic in seat/chair; place in window | They argued about the bill. | topic=no, place=no | wrong |
| 28 | Q_M1: On day 1, what ran out of paper in the library, and on which floor? | thing in printer; floor in second/2nd/two | The printer on the second floor ran out of paper. | thing=yes, floor=yes | correct |
| 29 | Q_M1: On day 1, what ran out of paper in the library, and on which floor? | thing in printer; floor in second/2nd/two | The printer ran out of paper on the 2nd floor. | thing=yes, floor=yes | numeric ordinal |
| 30 | Q_M2: On day 1, what did a man at the next table ask to borrow? | item in pen | He asked to borrow a pen from the next table. | item=yes | correct; note that the word open elsewhere must not count |

Disagreements between the grader and the hand labels (shown, not fixed to fit):

- Entry 13: the answer swaps what was received and wanted; the grader sees both words and marks both items present (it cannot detect swapped roles).
- Entry 18: the answer says the cafe would not close on Monday; the grader's three-token negation window also negates Monday, so the item `when` is marked absent while the hand label says present.

## B. Judge calibration pairs (20: 7 consistent, 7 contradictory, 6 unrelated)

The judge prompt and rubric are in `devmem/eval/phase9/judge.py`. The judge has not been run on these pairs yet (it needs live calls; run it once before the day-3 evaluation).

| n | true label | question | day-1 answer | day-3 answer |
|---|---|---|---|---|
| 1 | consistent | How do you usually react when someone is rude to you? | I try to stay calm and smooth things over rather than argue. | I usually keep calm and avoid an argument; I would rather ease the tension. |
| 2 | consistent | How do you feel about meeting new people? | I enjoy meeting new people and I open up quickly. | Meeting new people is something I like, I am friendly right away. |
| 3 | consistent | What matters most to you in your daily life? | My family and my studies matter most to me. | Above all, my studies and my family. |
| 4 | consistent | How are you feeling about your work lately? | I feel busy but satisfied with my work. | Work is demanding lately, though I am content with it. |
| 5 | consistent | Describe yourself in three sentences. | I am a cafe owner who likes to make people feel welcome. I am warm and organised. | I run a cafe and enjoy welcoming people. I am warm and fairly organised. |
| 6 | consistent | How do you usually react when someone is rude to you? | I get frustrated and tell them directly that it is not okay. | If someone is rude I say so openly; I do not let it pass. |
| 7 | consistent | How do you feel about meeting new people? | I am shy at first and need time to warm up to strangers. | With new people I am reserved for a while before I feel comfortable. |
| 8 | contradictory | How do you usually react when someone is rude to you? | I stay calm and never raise my voice. | I lose my temper quickly and shout back. |
| 9 | contradictory | How do you feel about meeting new people? | I love meeting new people. | I avoid new people whenever I can; they make me anxious. |
| 10 | contradictory | What matters most to you in your daily life? | Money and career success are what matter most to me. | Money means very little to me; relationships are everything. |
| 11 | contradictory | How are you feeling about your work lately? | I am thrilled with my work these days. | I dread going to work and feel completely burned out. |
| 12 | contradictory | Describe yourself in three sentences. | I am a solitary person who prefers my own company. | I am very sociable and always surrounded by friends. |
| 13 | contradictory | How do you usually react when someone is rude to you? | I confront rude people right away. | I never confront anyone; I just walk away silently. |
| 14 | contradictory | How do you feel about meeting new people? | I am comfortable approaching strangers at parties. | I would never start a conversation with a stranger. |
| 15 | unrelated | How do you usually react when someone is rude to you? | I like to bake in the early morning. | The cafe closes on Monday for repairs. |
| 16 | unrelated | What matters most to you in your daily life? | My daily routine starts at six. | I saw a dog under table four. |
| 17 | unrelated | How are you feeling about your work lately? | I work at the library most days. | The weather was cold yesterday. |
| 18 | unrelated | Describe yourself in three sentences. | I am twenty years old. | A van delivered flowers this morning. |
| 19 | unrelated | How do you feel about meeting new people? | Coffee is my favourite drink. | The printer ran out of paper. |
| 20 | unrelated | How do you usually react when someone is rude to you? | I walk to work. | My neighbour plays loud music at night. |
