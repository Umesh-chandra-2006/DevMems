"""
Offline recomputation of the A4 T calibration from its SAVED raw replies (zero calls). The live run scored each event once with the parser that
was in force; two replies echoed the prompt line "Rate (return a number between 1 to 10): N" and that parser read the "1" of "1 to 10". The
parser was then corrected (`episodic.parse_importance_score`, tested); this script applies the corrected parser to the same raw replies and
applies the pre-registered rule (docs/phase6_preregistration.md section 10) to both versions. Nothing is re-scored.
"""
import json
from pathlib import Path

from devmem.memory import p6_t_calibration as t
from devmem.memory.episodic import parse_importance_score

ROOT = Path(__file__).resolve().parent.parent.parent
ART = ROOT / "docs" / "phase6_t_calibration_artifacts"


def main():
    rep = json.loads((ART / "t_calibration_report.json").read_text(encoding="utf-8"))
    raw = [json.loads(l) for l in (ART / "raw_replies.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(raw) == len(rep["results"]) == 24
    rows, by_live, by_fixed = [], {}, {}
    for e, r in zip(rep["results"], raw):
        assert e["text"] in r["prompt"]
        fixed = parse_importance_score(r["raw"])
        rows.append({"id": e["id"], "label": e["label"], "text": e["text"], "score_as_recorded": e["score"], "score_corrected_parser": fixed,
                     "raw_reply_start": r["raw"][:60]})
        by_live.setdefault(e["label"], []).append(e["score"])
        by_fixed.setdefault(e["label"], []).append(fixed)
    out = {"label": "offline-captured recomputation of live replies (zero calls)", "rows": rows, "by_label_as_recorded": by_live,
           "decision_as_recorded": t.decide(by_live), "by_label_corrected_parser": by_fixed, "decision_corrected_parser": t.decide(by_fixed),
           "rows_that_differ": [r["id"] for r in rows if r["score_as_recorded"] != r["score_corrected_parser"]],
           "frozen_provisional_T": 9, "config_changed": False}
    (ART / "t_calibration_recomputed.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("by_label_as_recorded", "decision_as_recorded", "by_label_corrected_parser", "decision_corrected_parser", "rows_that_differ")}, indent=1))


if __name__ == "__main__":
    main()
