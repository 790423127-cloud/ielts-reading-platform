# Architecture

## Ownership

- Next.js App Router is the only frontend route authority.
- FastAPI is the only business-rule authority.
- The database is accessed through repositories created during request handling, never during module import.
- Shared contracts describe transport shapes; they do not contain scoring algorithms.

## Non-negotiable boundaries

1. Public question payloads do not contain answer keys, evidence or explanations.
2. Standard answers and scoring remain server-side.
3. AI output cannot change answers, raw scores, Band or mastery.
4. Full mock AI help is rejected while the session is in progress.
5. Only a complete 40-question GT Reading submission may return a Band estimate.
6. All future learner records carry `user_id` even while the first administrator account has unlimited usage.

## Frontend

Each URL is a Next.js route. Pages may compose feature components, but features must not install global `hashchange`, `popstate` or full-document `MutationObserver` handlers. Navigation highlighting comes from `usePathname`.

## Backend

The target layers are:

```text
api routers -> application services -> domain rules -> repositories
```

The existing FastAPI logic will be migrated behind `/api/v1` endpoints and verified against frozen legacy fixtures.

## Legacy policy

The following are reference-only and must not be copied into the new runtime:

- `v311-router.js`;
- `v320-nav-guard.js`;
- release-number UI patch layers;
- non-executing historical resource comments;
- module-specific hash listeners;
- DOM sibling cleanup that hides unknown nodes.
