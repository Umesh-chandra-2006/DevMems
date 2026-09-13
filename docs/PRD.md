# DevMem-Agents: Product Requirements Document (PRD)

**Audience:** Senior Developer (Gemini 3.8 Flash / Antigravity) and Junior Developer (Big Pickle / OpenCode). This document defines what you are building, your role in building it, and the process you must follow. It does not include full project rationale or design history, only what you need to execute correctly.

---

## 1. Project Summary

DevMem-Agents upgrades the memory system of an existing, published multi-agent LLM simulation (Stanford's "Generative Agents," Smallville). The original system stores all agent memories in one flat, undifferentiated stream. This project replaces that flat stream with a four-stage developmental memory architecture: seeded personality priors, persona-conditioned episodic memory, sleep-triggered semantic consolidation, and identity-level memory with dual promotion pathways. The simulation environment itself (Smallville) is reused unmodified; only the memory subsystem is being rebuilt.

Full architectural detail, data schemas, and pseudocode for every component live in `technical_implementation_plan.md`. That document is the binding technical spec. This PRD governs process, roles, and approval flow, not implementation detail.

Zero-cost constraint: all LLM inference runs on free-tier APIs (Groq, Gemini, NVIDIA NIM/Nemotron), accessed through a custom fallback router with multi-key rotation. No paid API usage is permitted anywhere in this project.

---

## 2. Hierarchy

This hierarchy is fixed for the entire project and applies without exception, regardless of how confident any party is that a step can be skipped.

```
Project Owner (Umesh)
        |
Project Manager (Claude) — advisory, reviews architecture and phase reports
        |
Senior Developer (Gemini 3.8 Flash, via Antigravity)
        |
Junior Developer (Big Pickle, via OpenCode)
```

- The **Junior Developer** reports to the **Senior Developer**. No task is considered complete until the Senior Developer reviews and accepts it.
- The **Senior Developer** reports to the **Project Owner and Project Manager** (referred to together as "higher authority"). No phase is considered complete, and no new phase begins, until higher authority explicitly approves the phase report.
- The **Project Manager** does not write code directly into the repository. The Project Manager's role is to review architecture, catch deviation from the locked design, and advise the Project Owner on whether to approve a phase.
- The **Project Owner** holds final approval authority at every gate.

This chain is not a suggestion. A phase report sitting unapproved is a hard stop, work does not continue past it under any circumstance, including time pressure, apparent obviousness of next steps, or a developer's own confidence that the work is correct.

---

## 3. Roles and Responsibilities

### Senior Developer (Gemini 3.8 Flash / Antigravity)
- Owns all architecturally significant, long-horizon implementation: the LLM router, all four memory stages, the single integration point with the forked base repository.
- May delegate scoped, well-defined sub-tasks to the Junior Developer, writing each as a precise task spec.
- Reviews and is accountable for all Junior Developer output before it's included in a phase deliverable.
- Produces one Phase Report per phase (template in Section 6) and halts at the approval gate.
- Does not redesign architecture defined in `technical_implementation_plan.md`. Flags concerns in phase reports instead of silently deviating.

### Junior Developer (Big Pickle / OpenCode)
- Owns narrow, single-file or single-function tasks assigned directly, either by the Senior Developer or, occasionally, by the Project Owner.
- Does not modify files outside an assigned task's declared scope.
- Does not make architectural decisions or introduce new dependencies without asking first.
- Produces one Task Report per assigned task (template in Section 6) and waits for Senior Developer approval before considering the task closed.

### Project Manager (Claude)
- Maintains the full project context, design rationale, and history that neither developer agent has.
- Reviews phase reports for architectural drift against `plan.md` and `technical_implementation_plan.md` before the Project Owner approves.
- Helps the Project Owner convert upcoming work into precise task specs before assignment.
- Does not write implementation code into the project repository.

### Project Owner (Umesh)
- Holds final approval at every phase gate.
- Assigns phases and tasks (with Project Manager support in drafting specs).
- Only party with full context on why the project is shaped the way it is.

---

## 4. Phases

Each phase below maps directly to sections in `technical_implementation_plan.md`. A phase does not begin until the previous phase's report has been reviewed and explicitly approved by higher authority.

| Phase | Scope | Owner | Reference |
|---|---|---|---|
| 0 | Repo fork, folder structure setup, environment/dependency install | Senior Dev | Section 1 |
| 1 | LLM Router: single-provider call, key rotation, multi-provider fallback, usage tracking | Senior Dev (may delegate provider adapter stubs to Junior Dev) | Section 3 |
| 2 | Baseline validation: forked repo running end-to-end on free-tier stack, config toggle (`baseline` vs `staged`) scaffolded | Senior Dev | Section 4 |
| 3 | Stage 1: Priors module, persona config loading, baseline fairness injection | Senior Dev (persona YAML file creation may delegate to Junior Dev) | Section 5 |
| 4 | Stage 2: Episodic memory, persona-conditioned importance scoring, `consolidated` flag | Senior Dev | Section 6 |
| 5 | Stage 3: Sleep-trigger hook, embedding clustering, LLM summarization, consolidation sweep | Senior Dev | Section 7 |
| 6 | Stage 4: Reinforcement counters, dual promotion paths, feed-forward into scoring prompt | Senior Dev | Section 8 |
| 7 | Evaluation harness: recall accuracy, coherence tracker, efficiency logger | Senior Dev (individual test scripts may delegate to Junior Dev) | Section 9 |
| 8 | Visualization: React + Three.js town view, per-agent memory inspection panel | Senior Dev (component-level UI tasks may delegate to Junior Dev) | N/A, frontend scope |
| 9 | Full comparison runs, results compilation | Senior Dev | Section 9, checkpoints |

Checkpoint definitions for "phase complete" are listed in Section 10 of `technical_implementation_plan.md`. A phase report is not submitted until its checkpoint condition is actually met and verifiable, not merely believed to be met.

---

## 5. Reporting and Approval Protocol

1. Work is assigned as a written spec (task spec for Junior Dev, phase spec for Senior Dev), not a verbal or informal request.
2. The assigned developer completes the work strictly within scope.
3. The assigned developer produces a report using the template in Section 6.
4. The report goes up one level: Junior Dev → Senior Dev, Senior Dev → Project Owner/Project Manager.
5. The receiving party reviews against the spec and the locked architecture.
6. One of three outcomes:
   - **Approved**: next phase/task may begin.
   - **Revisions requested**: specific, itemized feedback returned, developer revises and resubmits, does not proceed to new work in the meantime.
   - **Rejected with reassignment**: task is respecified and reassigned.
7. No phase or task is ever silently marked complete. Approval is explicit, in writing, before progression.

---

## 6. Report Templates

### Phase Report (Senior Developer → Higher Authority)
```
PHASE: [number and name]
STATUS: Complete / Blocked / Partially complete

WHAT WAS BUILT:
[bullet list, file by file]

HOW IT MATCHES THE SPEC:
[explicit mapping to the relevant technical_implementation_plan.md section]

DEVIATIONS FROM SPEC (if any):
[what changed, why, and what alternative was considered]

JUNIOR DEVELOPER TASKS DELEGATED THIS PHASE (if any):
[task, output, your review notes]

TESTS RUN / VERIFICATION:
[what was checked, how, and result]

OPEN QUESTIONS FOR HIGHER AUTHORITY:
[anything requiring a decision before the next phase]

REQUEST: Approval to proceed to Phase [N+1]
```

### Task Report (Junior Developer → Senior Developer)
```
TASK: [as assigned]
STATUS: Complete / Blocked / Needs clarification

WHAT WAS CHANGED:
[file(s), specific changes]

WHY:
[brief rationale tied to the task spec]

DEVIATIONS FROM SPEC (if any):
[explicit, nothing silent]

OPEN QUESTIONS:
[anything unclear or requiring a decision]

REQUEST: Review and approval
```

---

## 7. Non-Negotiable Rules (apply to both developers, all phases)

- No proceeding past an unapproved phase or task, regardless of confidence in correctness.
- No architectural decisions outside what `technical_implementation_plan.md` already specifies, without flagging it upward first.
- No silent full-file rewrites where a targeted edit would do, if a full rewrite is genuinely required, say so explicitly in the report.
- No new dependencies, libraries, or paid API usage without approval.
- No modification to `reverie/` (the forked base repo) outside the single integration point defined in the technical plan.
- Every deviation from spec, however small, gets written down. Undocumented deviation is treated as a process failure even if the resulting code works.
