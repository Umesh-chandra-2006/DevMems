"""
Answer harness over a checkpoint copy. For each authored question it retrieves from the agent's OWN memory (upstream `new_retrieve`, the same top-k for both arms, on a
copy of the checkpoint so the live run is never touched and `last_accessed` updates stay in the copy), builds one fixed answering prompt, and makes ONE call (purpose
`eval_recall` or `eval_probe`) through the injected call function. Answers are graded by devmem/eval/phase9/grader.py. Retrieval and persona loading are injectable so the
harness can be tested without network or a persona; the default loaders need the upstream backend on sys.path and REAL embeddings (an offline 768-dimensional fallback is not
comparable with the stored 3,072-dimensional vectors): the default path is NOT exercised by the offline tests and is to be run once on the pilot checkpoint before use.
"""
from typing import Any, Callable, Dict, List, Optional

from devmem.eval.phase9 import grader

TOP_K = 30   # upstream's default n_count for new_retrieve; identical for both arms

ANSWER_PROMPT = (
    "You are {name}. These are things you remember, from most to least relevant:\n{memories}\n\n"
    "Answer the question from your memories only, in one or two sentences. If you do not remember, say that you do not remember.\n"
    "Question: {question}\nAnswer:"
)


def build_answer_prompt(name: str, memories: List[str], question: str) -> str:
    mem = "\n".join(f"- {m}" for m in memories) if memories else "- (no relevant memory)"
    return ANSWER_PROMPT.format(name=name, memories=mem, question=question)


def default_retrieve(persona: Any, question: str, k: int = TOP_K) -> List[str]:
    from persona.cognitive_modules.retrieve import new_retrieve
    got = new_retrieve(persona, [question], n_count=k)
    nodes = got.get(question, [])
    return [getattr(n, "description", str(n)) for n in nodes]


def answer_questions(name: str, questions: List[Dict[str, Any]], call_fn: Callable[[str], str], persona: Any = None,
                     retrieve_fn: Optional[Callable[[Any, str, int], List[str]]] = None, k: int = TOP_K) -> List[Dict[str, Any]]:
    retrieve_fn = retrieve_fn or default_retrieve
    out = []
    for q in questions:
        mems = retrieve_fn(persona, q["question"], k)
        prompt = build_answer_prompt(name, mems, q["question"])
        ans = call_fn(prompt)
        g = grader.grade(ans, q["checklist"]) if q.get("checklist") else None
        out.append({"question_id": q["id"], "agent": name, "retrieved_count": len(mems), "answer": ans, "grade": g, "prompt_chars": len(prompt)})
    return out
