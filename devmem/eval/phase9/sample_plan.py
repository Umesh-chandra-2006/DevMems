"""
Fixed stratified sample for the replay controls (PM decision 2026-10-08): 300 events per condition = ALL 27 injected events plus 273 natural events stratified by
agent and by simulated day. The seed and the rule are committed NOW, before any run data is looked at; the function is deterministic.

Rule (stated in full):
  * natural events = the staged arm's importance-scoring events (agent, simulated time, text) that are not injected events;
  * strata = (agent, simulated day), 9 strata in the sorted order (agent name, day);
  * base quota = 273 // 9 = 30 per stratum, and the remaining 273 - 270 = 3 go one each to the first 3 strata in that order;
  * a stratum with fewer events than its quota gives all of them, and the shortfall is shared one at a time, in stratum order, among strata that still have unused events;
  * inside a stratum events are ordered by (simulated time, text) and chosen by a random.Random(SEED + stratum index) shuffle, then sorted back by time.
"""
import random
from typing import Dict, List, Sequence, Tuple

SEED = 20261008
N_TOTAL, N_INJECTED = 300, 27
N_NATURAL = N_TOTAL - N_INJECTED          # 273


def day_of(sim_time: str) -> int:
    d = int(sim_time[8:10]) - 13 + 1       # run start 2023-02-13
    return max(1, d)


def stratify(natural: Sequence[Tuple[str, str, str]]) -> Dict[Tuple[str, int], List[Tuple[str, str, str]]]:
    out: Dict[Tuple[str, int], List[Tuple[str, str, str]]] = {}
    for ev in natural:
        out.setdefault((ev[0], day_of(ev[1])), []).append(ev)
    return {k: sorted(v, key=lambda e: (e[1], e[2])) for k, v in sorted(out.items())}


def quotas(sizes: List[int], total: int = N_NATURAL) -> List[int]:
    n = len(sizes)
    base = [total // n] * n
    for i in range(total - sum(base)):
        base[i] += 1
    q = [min(b, s) for b, s in zip(base, sizes)]
    short = total - sum(q)
    while short > 0:
        moved = False
        for i in range(n):
            if short > 0 and q[i] < sizes[i]:
                q[i] += 1
                short -= 1
                moved = True
        if not moved:
            break
    return q


def build_sample(natural: Sequence[Tuple[str, str, str]], injected: Sequence[Tuple[str, str, str]], seed: int = SEED) -> Dict[str, object]:
    """natural and injected are lists of (agent, sim_time 'YYYY-MM-DD HH:MM:SS', text). Returns the chosen events and the allocation."""
    strata = stratify(natural)
    keys = list(strata)
    q = quotas([len(strata[k]) for k in keys])
    chosen: List[Tuple[str, str, str]] = []
    alloc = {}
    for i, k in enumerate(keys):
        rng = random.Random(seed + i)
        pool = list(strata[k])
        rng.shuffle(pool)
        pick = sorted(pool[:q[i]], key=lambda e: (e[1], e[2]))
        chosen += pick
        alloc[f"{k[0]}|day{k[1]}"] = {"available": len(strata[k]), "quota": q[i], "chosen": len(pick)}
    return {"seed": seed, "injected": sorted(injected, key=lambda e: (e[1], e[2])), "natural": chosen, "allocation": alloc,
            "n_injected": len(injected), "n_natural": len(chosen), "n_total": len(injected) + len(chosen)}
