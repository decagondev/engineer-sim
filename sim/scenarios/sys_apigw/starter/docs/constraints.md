# Constraints (known)

- **Regions:** us-east and eu. Cross-region Redis on every request is already a complaint.
- **Legal:** 429 bodies must not mention other tenants.
- **Sales:** one side letter says "unlimited" (Acme). That is political, not a default.
- **Ops:** Moe wants a kill switch that is not a deploy.
- **Stack:** nginx at the edge, app boxes, Redis, Postgres. No service mesh.
