# Legacy asset inventory

## Migrate as business assets

- verified question-bank JSON and identifiers;
- answer normalizers and deterministic scoring rules;
- complete 40-question Band conversion;
- Session and idempotent submission semantics;
- 17 exact subtype registry;
- seven ability mappings and verified generators;
- method-course content;
- evidence, paraphrase and local-analysis fields;
- mastery and review-schedule rules;
- verified sentence pack and fixed scoring;
- migration fixtures and regression expectations.

## Rebuild behind clean interfaces

- exam workspace;
- wrong-question presentation;
- learning-plan pages;
- sentence pages;
- teacher/report pages;
- API transport and repository boundaries.

## Do not migrate into the runtime

- `static/v311-router.js`;
- `static/v320-nav-guard.js`;
- old navigation wrappers;
- release-version CSS/JS patch identity;
- non-executing historical resource markers;
- broad MutationObservers used for navigation or component discovery;
- sibling-node cleanup used to classify unknown UI as legacy;
- localStorage learning-plan authority already replaced by the backend.
