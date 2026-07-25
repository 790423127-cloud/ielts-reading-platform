# Question-bank migration

The legacy source is private and its JSON must not be reconstructed manually. The importer copies the original UTF-8 bytes and validates the frozen catalogue before the new runtime accepts the bank.

Expected inventory:

- 46 complete GT Reading tests;
- 3 Parts per test;
- 40 questions per test;
- 1,840 questions total;
- IDs from `b10-test-a` through `b21-test-4` in the frozen index order.

Run from a workspace containing both repositories:

```bash
python scripts/import_legacy_question_bank.py \
  --source ../ielts-g-reading-ai-coach/data \
  --destination services/api/data/question-bank
```

Use `--check` first to validate without copying. The generated `migration_manifest.json` records SHA-256 for every source file.

The API remains deliberately unavailable with HTTP 503 until all 46 files are present. Public test payloads remove standard answers, accepted answers, evidence, analysis, paraphrases, keywords and wrong-option explanations. Server scoring loads a separate authoritative copy.
