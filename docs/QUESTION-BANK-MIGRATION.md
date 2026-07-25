# Question-bank migration

The legacy source is private and its JSON must not be reconstructed manually. The importer copies the original UTF-8 bytes and validates the frozen catalogue before the new runtime accepts the bank.

## Repository boundary

`ielts-reading-platform` is currently public. Verified IELTS source text, questions, answers, evidence and translations must not be committed to this repository unless its visibility and content rights have been reviewed first.

The default local path `services/api/data/question-bank/` is ignored by Git. Production must provide the same directory through one of these private mechanisms:

- a private deployment volume;
- private object storage downloaded during a protected deployment step;
- a separate private content repository checked out with a read-only deployment credential.

The application code may remain public; the licensed/private content remains separate.

## Expected inventory

- 46 complete GT Reading tests;
- 3 Parts per test;
- 40 questions per test;
- 1,840 questions total;
- IDs from `b10-test-a` through `b21-test-4` in the frozen index order.

Run from a private workspace containing both repositories:

```bash
python scripts/import_legacy_question_bank.py \
  --source ../ielts-g-reading-ai-coach/data \
  --destination services/api/data/question-bank
```

Use `--check` first to validate without copying. The generated `migration_manifest.json` records SHA-256 for every source file. Do not use `git add -f` on this directory in the public application repository.

The API remains deliberately unavailable with HTTP 503 until all 46 files are present. Public test payloads remove standard answers, accepted answers, evidence, analysis, paraphrases, keywords and wrong-option explanations. Server scoring loads a separate authoritative copy.
