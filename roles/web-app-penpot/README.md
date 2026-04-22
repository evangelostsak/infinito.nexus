# Penpot

## Description

Penpot is an open-source design and prototyping platform for collaborative UI/UX work.

## Overview

This role deploys Penpot as a multi-container stack (frontend, backend, exporter) integrated with shared PostgreSQL, Redis, and MinIO services in Infinito.Nexus.

## Prerequisites

- `web-app-minio` must be available for S3-compatible object storage.
- PostgreSQL and Redis shared services must be enabled for this app.
- Role credentials must be generated before first deploy:
  - `credentials.secret_key`
  - `credentials.objects_access_key`
  - `credentials.objects_secret_key`
  - `credentials.objects_bucket_name`

## Deployment

Initial baseline deploy:

```bash
make deploy-fresh-purged-apps APPS=web-app-penpot FULL_CYCLE=true
```

Follow-up loop:

```bash
make deploy-reuse-kept-apps APPS=web-app-penpot
```

## Validation

- Service reachability:

```bash
curl -k https://penpot.design.${DOMAIN_PRIMARY}
```

- Role-local Playwright validation is available through `roles/web-app-penpot/files/playwright.spec.js` with `templates/playwright.env.j2`.

## References

- https://help.penpot.app/technical-guide/configuration/
- https://github.com/penpot/penpot
