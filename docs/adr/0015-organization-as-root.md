# ADR-0015: Organization as the root of every entity

- Status: accepted · Date: 2026-10-31

## Context
The project owner wants the option to offer DexterHouse as SaaS. Adding the tenant later means migrating every table and reviewing every query. In self-hosted mode the user does not need multi-tenancy.

## Decision
Every root entity (Project, installed Package, model profiles, budgets, API tokens, users via membership) has an `organization_id`. A default `QuerySet` manager filters by the request's organization; tests verify that no endpoint returns another organization's data. No tenant management UI or billing in 1.0; self-hosted installations create `default` on first start.

## Alternatives considered
- No tenant: painful migration later.
- Full multi-tenancy with billing: out of scope and costly now.
- One Postgres schema per tenant: strong isolation, but complicates migrations and Celery.

## Consequences
+ Moving to SaaS touches authentication, billing and UI, not the data model.
− One extra column and filter everywhere; discipline in tests (`pytest` fixture with two organizations).
