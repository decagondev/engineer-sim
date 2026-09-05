# Current system

Marketing currently pastes bit.ly links into ads. Legal is tired of a third party
seeing click data. There is no first-party shortener.

**What we run today**
- App traffic: a couple of stateless API boxes behind nginx.
- Postgres 14, one primary, nightly logical backups. Used by the product.
- Redis: used for session cache. Memory is already "a bit tight" in Cole's words.
- Observability: logs in one place, no dedicated tracing for a new edge service.

**What we do not have**
- A multi-region story.
- A dedicated edge/CDN config we own (marketing sometimes puts CloudFront on static sites).
- An ID service or ticket server.

Anything you propose should say whether it sits on this stack or needs something new.
