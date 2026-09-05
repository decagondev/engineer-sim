# Current system

Teams send mail from app processes. Checkout retries have sent the same receipt
three times. Password reset uses Sendgrid directly. Marketing dumps CSVs into
a Sendgrid campaign. Push is a half-finished FCM wrapper on one service.
SMS is a script on someone's laptop for "urgent" fraud alerts.

**Shared infra:** Postgres, a Rabbit-like queue used by search indexing, Redis.
No dedicated notification topic. No global user-preference table that anyone
trusts.
