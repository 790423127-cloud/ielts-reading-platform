# Migration plan

Source baseline: `790423127-cloud/ielts-g-reading-ai-coach@6b8cf1221736414fcc4fec6c3420cc4e66df98ce`.

## Phase 0 — platform bootstrap

- Next.js App Router and one navigation source;
- FastAPI `/api/v1` application;
- shared transport contracts;
- CI for TypeScript build and Pytest;
- explicit security boundaries;
- no legacy route or DOM patch code.

Exit condition: both applications build, health import opens no database, and the architecture tests reject legacy route listeners.

## Phase 1 — question bank, scoring and Session parity

Migrate:

- verified question-bank loader;
- exact answer normalization;
- deterministic raw scoring;
- complete 40-question GT Band conversion;
- Session creation, draft and idempotent submission;
- public payload answer isolation;
- historical Session read model.

For every frozen fixture:

```text
same test + same answers -> identical correct count, per-question correctness and Band
```

No UI replacement occurs until parity is complete.

## Phase 2 — exam workspace

- part practice;
- complete mock;
- timer;
- draft recovery;
- part navigation;
- annotations and flags;
- submitted result and history.

## Phase 3 — learning loop

- complete local review;
- 17 exact subtypes;
- method courses;
- seven deterministic ability trainings;
- return to original wrong question;
- validation attempts.

## Phase 4 — mastery and sentences

- backend learning tasks and mastery;
- cross-date review;
- due review;
- fixed verified sentence training;
- personal sentences and source context.

## Phase 5 — new features on the new architecture

- free-text AI teacher for wrong questions, sentences and plans;
- conversation history, summaries, cache and cost audit;
- vocabulary capture and JSON/CSV/TXT export;
- no voice implementation.

## Phase 6 — commercial readiness

- authentication and user ownership;
- administrator unlimited plan;
- subscription and entitlements;
- rate/cost policy for paid users;
- privacy export and deletion;
- content-rights audit;
- observability, backup and recovery.

## Cutover

The old application remains available until all required routes pass desktop and 390px mobile checks. The new application first uses a separate test database, then imports a verified snapshot. The old application becomes read-only before final cutover and remains available for rollback during the defined observation period.
