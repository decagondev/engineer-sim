# Current system

Public API is nginx → app. There is a crude global connection cap that did
nothing in the last incident (one tenant, many connections, still "fair" at
the box). API keys map to tenants in Postgres. Billing knows free / pro /
enterprise; "unlimited" is not a field, it is a PDF.

Last incident: free-tier scraper, enterprise tenant 5xx, 40 minutes, no
per-tenant dashboard.
