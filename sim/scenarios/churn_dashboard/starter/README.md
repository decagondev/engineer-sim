# Customer health — starter repo

You've been asked to help Priya (Head of Customer Success). Talk to her first —
there's a ticket below, but tickets are rarely the whole story.

## The ask (as written)
> "Can we get a dashboard showing how our customers are doing? Charts, maybe a
> weekly email. — Priya"

## What's in here
- `data/usage_export.csv` — product usage, one row per account per week (from Postgres).
- `data/stripe_invoices.csv` — billing/plan info (from Stripe).
- `src/analysis.py` — an empty stub to start from.

## Heads up
The two data sources don't share a key cleanly. Usage uses `account_id`
(e.g. `acct_1042`); Stripe uses `customer_id` (e.g. `cus_JX92`). There's no
mapping table in here. Part of the job is figuring out what's actually worth
building given that.

Commit as you go — your git history is part of how the work is reviewed.
