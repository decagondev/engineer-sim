"""Generate the 20 interview-assessment scenarios. Run from repo root."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "sim" / "scenarios"

DESIGN_MD = """# System design

Interview: {title}
Author: (you)
Timebox: ~20 minutes

## 1. Problem (in your words)

## 2. Clarifying questions I asked / answers I used

## 3. Requirements
### Functional
### Non-functional (scale, latency, consistency, availability)
### Non-goals (v1)

## 4. Capacity sketch
| Signal | Estimate | Notes |
| --- | --- | --- |
| QPS |  |  |
| Storage |  |  |
| Payload size |  |  |

## 5. API

## 6. High-level architecture
<!-- Components and how a request flows. Your AI will draw a mermaid diagram from this. -->

## 7. Data model

## 8. Key decisions and trade-offs
| Decision | Alternatives I considered | Why this |
| --- | --- | --- |
|  |  |  |

## 9. Failure modes
| Failure | User impact | Mitigation |
| --- | --- | --- |
|  |  |  |

## 10. What I would not build in v1

## 11. Open questions
-
"""

TICKETS_MD = """# Implementation tickets (extra credit)

Write tickets so an engineer who has **only this file** (not the design doc)
could implement the system. Each ticket needs context, interfaces, data shape,
and acceptance criteria.

The grader can include or ignore this portion — it is extra credit.
"""

README_TMPL = """# {title}

This is a **timed system-design interview** (~20 minutes from start to submit).

1. Open **Team Chat**. The interviewer will present the problem.
2. Ask clarifying questions. They will answer facts, not the architecture.
3. Write a detailed, understandable design in `DESIGN.md`.
4. Submit `DESIGN.md` (Submit app), then tell the interviewer you are done.
5. An assessor will ask you to defend *your* document — not a textbook answer.
6. Optional extra credit: implementation tickets in `TICKETS.md` / the Tickets app
   that are clear enough to build from without the design doc.

You are the candidate. Do not expect the interviewer to hand you the design.
"""

BRIEF_TMPL = """# Interview notes

- Timebox: about 20 minutes to a submitted design.
- The interviewer will not outline the architecture.
- Hidden constraints exist; you have to ask for them.
- After you submit, you will defend *your* document.
"""

SRC_README = """# Notes

This interview is document-first. Implementation tickets (extra credit) should
be specific enough that this folder could be filled in from the tickets alone.
"""

# Each entry: enough for a staff engineer to start; hidden_* is extractable
# facts, not a model architecture.
SCENARIOS = [
    dict(
        key="iv_unique_id",
        title="Interview: unique IDs for the write path",
        difficulty="junior",
        who=("elena", "Elena", "Staff interviewer"),
        problem=(
            "We need a service that issues unique IDs for every write in our "
            "product. Walk me through how you would design it. You have about "
            "twenty minutes: ask what you need, then write the design."
        ),
        hidden_need=(
            "About 10k IDs/sec at peak, IDs should be roughly time-ordered so "
            "new rows sort near the end of an index, 64-bit is preferred, and "
            "we will add a second region later."
        ),
        hidden_constraints=(
            "No new vendor. Existing Postgres and a small Redis. Clock skew "
            "across boxes is a few tens of milliseconds. IDs must not collide."
        ),
        rungs=[
            ("asks about rate, QPS, volume, or how many IDs",
             "Peak is on the order of ten thousand IDs a second. Average is much lower."),
            ("asks about ordering, sorting, or whether IDs should be sequential",
             "We want new IDs to be roughly time-ordered so recent writes land near "
             "the end of an index. Strict sequential is not required."),
            ("asks about size, format, regions, or multi-datacenter",
             "64-bit would fit our columns. A second region is on the roadmap; "
             "v1 can be one region if you say how you would extend it."),
        ],
        discovery="Asked enough to learn rate, time-order, bit width, and a future second region — not 'just a UUID column'.",
        scoping="Wrote a design that can issue unique IDs at the stated rate and names collision / clock behaviour.",
        stakeholders="Treated it as a system (generator, uniqueness, failure) rather than a one-liner.",
        communication="Defended their ID scheme from their own document without needing the assessor to invent it.",
        ticket="Write implementation tickets for the ID service",
    ),
    dict(
        key="iv_rate_limiter",
        title="Interview: rate limiter in front of the public API",
        difficulty="mid",
        who=("omar", "Omar", "Staff interviewer"),
        problem=(
            "Design a rate limiter for our public HTTP API. I want to hear how "
            "you would approach it and what you would write down for the team. "
            "About twenty minutes."
        ),
        hidden_need=(
            "Per-API-key limits, default 100 requests/minute, some keys need "
            "custom limits, and we must not take the API down if the limiter is sick."
        ),
        hidden_constraints=(
            "Several API boxes already; they do not share memory. A small Redis "
            "exists. Limits should be eventually consistent enough that a brief "
            "overshoot is acceptable. No new vendor."
        ),
        rungs=[
            ("asks whose traffic, per user / IP / key, or the unit of limiting",
             "Per API key. IP is a nice-to-have, not v1."),
            ("asks about the limit, window, or burst",
             "Default is 100 requests per minute. A few partners will need a higher cap."),
            ("asks what happens when the limiter is down, or about fail-open / fail-closed",
             "If the limiter is sick we would rather serve traffic than go dark. "
             "A short overshoot is fine."),
        ],
        discovery="Extracted per-key limits, the default window, custom caps, and fail-open.",
        scoping="Designed a limiter that works across multiple boxes and names the fail path.",
        stakeholders="Showed they know a limiter is a distributed decision, not a local counter.",
        communication="Defended window, store, and fail-open/closed from their write-up.",
        ticket="Write implementation tickets for the rate limiter",
    ),
    dict(
        key="iv_key_value",
        title="Interview: tiny key-value store",
        difficulty="mid",
        who=("priya", "Priya", "Staff interviewer"),
        problem=(
            "Design a small key-value store our internal services can call. "
            "Not Redis-the-product — your design. Twenty minutes: questions, "
            "then a written design."
        ),
        hidden_need=(
            "Get/put/delete of blobs up to 16KB, ~5k QPS mostly gets, and a "
            "value should still be there after a process restart."
        ),
        hidden_constraints=(
            "One availability zone for v1. Replication can wait. We have disks "
            "and a couple of boxes. Strong consistency for a single key is expected."
        ),
        rungs=[
            ("asks about operations, value size, or the API",
             "Get, put, delete. Values are small — think 16KB max, usually much less."),
            ("asks about QPS, read/write mix, or latency",
             "On the order of five thousand requests a second, mostly gets. "
             "A few milliseconds is fine."),
            ("asks about durability, restart, or replication",
             "A process restart must not lose data. One AZ for v1; we can talk "
             "about replicas as a later step."),
        ],
        discovery="Got ops, size, read-heavy load, and durability-after-restart.",
        scoping="Wrote a store design with a persistence story and a single-key consistency stance.",
        stakeholders="Covered API, data, and failure, not just 'use a hashmap'.",
        communication="Explained their persistence and eviction (or lack of it) from the doc.",
        ticket="Write implementation tickets for the key-value store",
    ),
    dict(
        key="iv_pastebin",
        title="Interview: pastebin for the company",
        difficulty="junior",
        who=("nate", "Nate", "Staff interviewer"),
        problem=(
            "Design a pastebin: people paste text, get a link, others read it. "
            "Treat it as a real service. You have about twenty minutes."
        ),
        hidden_need=(
            "Pastes expire (default 7 days, optional never), some pastes should "
            "be burn-after-read, and we expect a few million pastes with a heavy "
            "read/write imbalance toward reads of recent pastes."
        ),
        hidden_constraints=(
            "No login in v1. Max paste 1MB. Public links are fine; we will regret "
            "unlisted-but-guessable IDs. Existing object store is available."
        ),
        rungs=[
            ("asks about expiry, lifetime, or deletion",
             "Default expire in a week. Some people will want 'keep forever' and "
             "a few will want burn-after-read."),
            ("asks about size, login, or privacy",
             "No accounts in v1. Cap a paste at a megabyte. Links are public if you have them."),
            ("asks about volume, traffic, or how pastes are read",
             "A few million pastes over time. Recent ones get almost all the reads."),
        ],
        discovery="Extracted expiry options, burn-after-read, size cap, and read-heavy recent pastes.",
        scoping="Designed create/read/expire with an ID story that is not trivially guessable.",
        stakeholders="Included data lifetime and a v1 cut (no accounts).",
        communication="Defended storage, IDs, and expiry from their document.",
        ticket="Write implementation tickets for the pastebin",
    ),
    dict(
        key="iv_url_shortener",
        title="Interview: URL shortener",
        difficulty="mid",
        who=("sia", "Sia", "Staff interviewer"),
        problem=(
            "Design a URL shortener. Classic interview, but I want a design "
            "document the team could implement from — not a whiteboard speech. "
            "About twenty minutes."
        ),
        hidden_need=(
            "100 creates/sec, 10k redirects/sec, redirects should be fast, and "
            "we need a daily click count per link — not a live dashboard."
        ),
        hidden_constraints=(
            "Custom aliases are a v1 request from marketing. Open-redirect abuse "
            "will happen. One existing Postgres and a small cache."
        ),
        rungs=[
            ("asks about create vs redirect volume or QPS",
             "Creates are modest — about a hundred a second. Redirects are the "
             "hot path, on the order of ten thousand a second."),
            ("asks about analytics, clicks, or reporting",
             "A click count per link by the next morning is enough. Not live."),
            ("asks about custom aliases, vanity URLs, or abuse",
             "Marketing wants optional custom slugs. People will try to short-link phishing URLs."),
        ],
        discovery="Got create/redirect rates, next-morning counts, custom aliases, and abuse.",
        scoping="Separated the redirect path from counting and named a v1 abuse stance.",
        stakeholders="Treated shortener as a read-heavy system with an ID and safety problem.",
        communication="Walked their own redirect and count path when asked.",
        ticket="Write implementation tickets for the shortener",
    ),
    dict(
        key="iv_web_crawler",
        title="Interview: polite web crawler",
        difficulty="senior",
        who=("dev", "Dev", "Staff interviewer"),
        problem=(
            "Design a crawler that fetches a seed list of sites and follows "
            "links so we can build a small index later. I care about how you "
            "would not get us banned. Twenty minutes to a written design."
        ),
        hidden_need=(
            "Tens of thousands of pages/day, must honour robots.txt and a "
            "per-host politeness delay, and we need to recrawl changed pages "
            "without refetching everything daily."
        ),
        hidden_constraints=(
            "A handful of worker boxes. Seed list is a few thousand domains. "
            "Legal wants a crawl-delay we can prove. Javascript-heavy pages "
            "are out of v1."
        ),
        rungs=[
            ("asks about volume, seeds, or how many pages",
             "Tens of thousands of pages a day from a seed list of a few thousand domains."),
            ("asks about robots.txt, politeness, rate, or getting blocked",
             "Honour robots.txt and a per-host delay. Legal wants us to be able to show we did."),
            ("asks about freshness, recrawl, or change detection",
             "We do not want to refetch the whole set every day — recrawl what changed."),
        ],
        discovery="Extracted daily volume, politeness/robots, and incremental recrawl.",
        scoping="Designed URL frontier, per-host throttling, and a recrawl story; JS out of v1.",
        stakeholders="Showed crawler design is scheduling and policy, not just HTTP get.",
        communication="Defended politeness and frontier choices from the write-up.",
        ticket="Write implementation tickets for the crawler",
    ),
    dict(
        key="iv_autocomplete",
        title="Interview: search box autocomplete",
        difficulty="senior",
        who=("mira", "Mira", "Staff interviewer"),
        problem=(
            "Design autocomplete for our product search box: user types, we "
            "suggest queries. I want the design written down. About twenty minutes."
        ),
        hidden_need=(
            "p95 suggestion latency under 50ms, top 10 suggestions, prefixes "
            "from a catalog of ~2 million queries, and we update the catalog daily."
        ),
        hidden_constraints=(
            "Typo-tolerance is nice-to-have, not v1. Personalized ranking is "
            "out. We can precompute offline. Traffic is bursty at business hours."
        ),
        rungs=[
            ("asks about latency, how many suggestions, or UX",
             "Ten suggestions. Users notice if it feels laggy — think under 50ms."),
            ("asks about the corpus, catalog, or where queries come from",
             "About two million historical queries we can use as the catalog."),
            ("asks about freshness, updates, or personalization",
             "A daily refresh of the catalog is fine. Do not personalize in v1."),
        ],
        discovery="Got latency, k=10, catalog size, and daily refresh / no personalization.",
        scoping="Designed a prefix path that can hit the latency bar and named what is offline.",
        stakeholders="Separated online path from catalog build.",
        communication="Explained their index and update story from the document.",
        ticket="Write implementation tickets for autocomplete",
    ),
    dict(
        key="iv_job_queue",
        title="Interview: background job queue",
        difficulty="mid",
        who=("cole", "Cole", "Staff interviewer"),
        problem=(
            "Services need to enqueue background work — send email, resize an "
            "image — and workers should pick it up. Design the queue. Twenty minutes."
        ),
        hidden_need=(
            "At-least-once is acceptable, jobs should retry with a cap, and a "
            "poison message must not stall the queue. A few hundred jobs/sec."
        ),
        hidden_constraints=(
            "Multiple producer services, multiple worker pools by job type. "
            "No cloud-vendor queue required if you can justify a simple one. "
            "Visibility timeout / ack is expected."
        ),
        rungs=[
            ("asks about volume or job types",
             "A few hundred jobs a second. Types include email and image resize; more will come."),
            ("asks about delivery, retries, or at-least-once vs exactly-once",
             "At-least-once is fine. Retry a few times, then dead-letter. Exactly-once is not required."),
            ("asks about poison messages, stuck jobs, or a bad payload",
             "A bad payload must not block the rest of the queue."),
        ],
        discovery="Extracted rate, at-least-once, retry/dead-letter, and poison isolation.",
        scoping="Designed enqueue/ack/retry and named a dead-letter path.",
        stakeholders="Treated a queue as a contract (visibility, ack), not a list.",
        communication="Defended delivery guarantees from their own write-up.",
        ticket="Write implementation tickets for the job queue",
    ),
    dict(
        key="iv_metrics",
        title="Interview: metrics ingest for product counters",
        difficulty="senior",
        who=("hana", "Hana", "Staff interviewer"),
        problem=(
            "Design a service that accepts product counters (button clicks, "
            "errors) from our apps and lets us read them back as time series. "
            "Twenty minutes to a design doc."
        ),
        hidden_need=(
            "On the order of 50k points/sec ingest, query is 'last hour / last "
            "day' dashboards, and we can lose a few seconds of data on a crash "
            "but not a whole day."
        ),
        hidden_constraints=(
            "Cardinality will explode if every user-id becomes a label — push "
            "back. One-second resolution is finer than we need. Existing object "
            "store for cold data is fine."
        ),
        rungs=[
            ("asks about ingest rate or how metrics arrive",
             "On the order of fifty thousand points a second from our apps."),
            ("asks about queries, dashboards, or retention",
             "People look at the last hour and the last day. Older than a couple "
             "of weeks can be coarse or gone."),
            ("asks about loss, durability, or cardinality / labels",
             "Losing a couple of seconds on a crash is OK. Losing a day is not. "
             "Please do not make every user id a label."),
        ],
        discovery="Got ingest rate, query windows, acceptable loss, and cardinality warning.",
        scoping="Designed ingest → store → query with aggregation and a cardinality stance.",
        stakeholders="Knew metrics systems die on cardinality and write amplification.",
        communication="Defended resolution, retention, and label policy from the doc.",
        ticket="Write implementation tickets for metrics ingest",
    ),
    dict(
        key="iv_webhooks",
        title="Interview: outbound webhook delivery",
        difficulty="senior",
        who=("joel", "Joel", "Staff interviewer"),
        problem=(
            "Customers want webhooks when something happens in our product "
            "(payment succeeded, seat added). Design delivery. Twenty minutes."
        ),
        hidden_need=(
            "At-least-once delivery, retries with backoff for hours, customers "
            "will have slow or down endpoints, and we must not let one customer "
            "block others."
        ),
        hidden_constraints=(
            "Signing the payload is expected. Ordering per resource is nice-to-have, "
            "not global. Volume is thousands of events/min, bursty. No 'infinite retry'."
        ),
        rungs=[
            ("asks about delivery guarantee, retries, or timeouts",
             "At-least-once. Retry with backoff for a few hours, then give up and mark failed."),
            ("asks about noisy / down customers or isolation",
             "Some endpoints will be slow or down for a day. They must not stall everyone else."),
            ("asks about signing, security, or ordering",
             "Sign the body so they can verify it is us. Per-resource order is nice; global order is not required."),
        ],
        discovery="Extracted at-least-once, bounded retries, isolation, and signing.",
        scoping="Designed a delivery worker path that isolates bad endpoints.",
        stakeholders="Treated webhooks as a reliability and abuse problem, not HTTP POST.",
        communication="Walked retry, signing, and isolation from their document.",
        ticket="Write implementation tickets for webhook delivery",
    ),
    dict(
        key="iv_file_upload",
        title="Interview: file upload and download",
        difficulty="mid",
        who=("rhea", "Rhea", "Staff interviewer"),
        problem=(
            "Users need to upload files (resumes, images) and download them "
            "later. Design that path. About twenty minutes."
        ),
        hidden_need=(
            "Files up to 100MB, we should not stream them through the app "
            "boxes if we can help it, and downloads need time-limited links."
        ),
        hidden_constraints=(
            "Existing object store. Virus scan is a v1 request from security "
            "but can be async. Metadata lives in Postgres. Hot linking is a concern."
        ),
        rungs=[
            ("asks about size, types, or how many files",
             "Up to a hundred megabytes. Images and PDFs mostly. Thousands of uploads a day, not millions."),
            ("asks whether files go through the API servers or direct to storage",
             "We would rather not drag 100MB through the app boxes if we can avoid it."),
            ("asks about access, expiry, hotlinking, or scanning",
             "Downloads should be time-limited links. Security wants a malware scan; it can happen after upload."),
        ],
        discovery="Got size, avoid app-box streaming, time-limited download, async scan.",
        scoping="Designed upload/download with object storage and a metadata record.",
        stakeholders="Separated metadata, bytes, and auth.",
        communication="Defended the upload handshake and link expiry from the doc.",
        ticket="Write implementation tickets for file upload",
    ),
    dict(
        key="iv_chat",
        title="Interview: one-to-one chat",
        difficulty="senior",
        who=("vik", "Vik", "Staff interviewer"),
        problem=(
            "Design one-to-one chat for our product: two people, message "
            "history, online enough to feel instant. Write the design. Twenty minutes."
        ),
        hidden_need=(
            "Hundreds of thousands of users, not millions of groups; p95 send "
            "under a couple of hundred milliseconds in-region; history should "
            "survive refresh; unread counts matter."
        ),
        hidden_constraints=(
            "No group chat in v1. Media attachments later. Exactly-once is not "
            "required if the UI can de-dupe. One region for v1."
        ),
        rungs=[
            ("asks about 1:1 vs groups, or scale of users",
             "One-to-one only. Hundreds of thousands of users, not a global public chat."),
            ("asks about latency, delivery, or what 'instant' means",
             "In-region it should feel instant — a couple of hundred milliseconds is the ballpark."),
            ("asks about history, unread, or attachments",
             "History on refresh. Unread counts yes. Attachments can wait."),
        ],
        discovery="Extracted 1:1, user scale, latency, history, and unread; groups/media out.",
        scoping="Designed send, fan-in to the other user, and a history store.",
        stakeholders="Covered online path vs stored history.",
        communication="Defended delivery and storage choices from their write-up.",
        ticket="Write implementation tickets for 1:1 chat",
    ),
    dict(
        key="iv_presence",
        title="Interview: online presence",
        difficulty="mid",
        who=("ada", "Ada", "Staff interviewer"),
        problem=(
            "We want a green dot: is this person online right now? Design "
            "presence. Twenty minutes, written design."
        ),
        hidden_need=(
            "Hundreds of thousands of clients, presence can be a bit stale "
            "(tens of seconds), and we must not heartbeat the database to death."
        ),
        hidden_constraints=(
            "'Last seen' is enough if live is expensive. Tabs and mobile will "
            "disconnect messily. No cross-region v1."
        ),
        rungs=[
            ("asks how fresh 'online' must be, or tolerance for staleness",
             "Tens of seconds late is fine. We are not building a game tick."),
            ("asks about scale of clients or connections",
             "Hundreds of thousands of clients could be connected at peak."),
            ("asks about last-seen vs live, or disconnects",
             "Last-seen is acceptable if live presence is costly. Mobile will drop without a clean goodbye."),
        ],
        discovery="Got staleness tolerance, client scale, and messy disconnects.",
        scoping="Designed a presence path that does not write the DB on every heartbeat.",
        stakeholders="Knew presence is a fan-out and TTL problem.",
        communication="Explained heartbeat, TTL, and last-seen from the document.",
        ticket="Write implementation tickets for presence",
    ),
    dict(
        key="iv_leaderboard",
        title="Interview: game leaderboard",
        difficulty="mid",
        who=("ken", "Ken", "Staff interviewer"),
        problem=(
            "Design a leaderboard: players submit scores, we show top N and "
            "a player's rank. Twenty minutes to a design doc."
        ),
        hidden_need=(
            "Top 100 is the common read, rank-for-one-player is needed, scores "
            "arrive in bursts after matches, and we reset weekly."
        ),
        hidden_constraints=(
            "Cheating / impossible scores will happen. Ties need a defined rule. "
            "Historical seasons can be archived. One game mode in v1."
        ),
        rungs=[
            ("asks about top-N, rank of a player, or read patterns",
             "People open the top hundred constantly. They also want 'what is my rank'."),
            ("asks about write rate, matches, or resets",
             "Scores arrive in bursts after matches. The board resets every week."),
            ("asks about ties, cheating, or seasons",
             "Define a tie-break. People will submit nonsense scores. Old weeks can be archived."),
        ],
        discovery="Extracted top-100, personal rank, bursty writes, weekly reset, ties/cheat.",
        scoping="Designed a board that can answer top-N and rank without a full table scan story.",
        stakeholders="Included reset and abuse, not just a sorted list.",
        communication="Defended the data structure and reset from the write-up.",
        ticket="Write implementation tickets for the leaderboard",
    ),
    dict(
        key="iv_search",
        title="Interview: product catalog search",
        difficulty="senior",
        who=("lina", "Lina", "Staff interviewer"),
        problem=(
            "Design search over our product catalog: type a query, get matching "
            "items. I want a written design. About twenty minutes."
        ),
        hidden_need=(
            "~500k products, p95 query under 200ms, filters (price, category), "
            "and the catalog updates throughout the day — not only nightly."
        ),
        hidden_constraints=(
            "Typo tolerance is expected at a basic level. Relevance can be "
            "simple in v1. We should not query Postgres LIKE on every keystroke."
        ),
        rungs=[
            ("asks about catalog size, latency, or filters",
             "About half a million products. Filters for price and category. "
             "Queries should feel fast — under a couple of hundred milliseconds."),
            ("asks about how often the catalog changes or indexing",
             "Products change through the day. A nightly-only index will look wrong."),
            ("asks about typos, ranking, or what 'good' results mean",
             "Basic typo tolerance yes. Fancy personalization can wait. Do not LIKE-scan Postgres."),
        ],
        discovery="Got catalog size, latency, filters, intra-day updates, and typo/no-LIKE.",
        scoping="Designed an index + query path and an incremental update story.",
        stakeholders="Separated search index from the source of truth.",
        communication="Explained indexing and filters from their document.",
        ticket="Write implementation tickets for catalog search",
    ),
    dict(
        key="iv_scheduler",
        title="Interview: delayed jobs / cron",
        difficulty="mid",
        who=("beau", "Beau", "Staff interviewer"),
        problem=(
            "We need to run work later: 'send this email in 30 minutes' or "
            "'every night at 02:00'. Design the scheduler. Twenty minutes."
        ),
        hidden_need=(
            "Mix of one-shot delays and recurring cron, tens of thousands of "
            "pending jobs, and a missed night job should still run (catch-up), "
            "not be silently skipped."
        ),
        hidden_constraints=(
            "Multiple scheduler boxes — no single node clock. At-least-once "
            "is OK. A thundering herd at midnight is a real risk."
        ),
        rungs=[
            ("asks about one-shot vs recurring, or the API",
             "Both: delay a one-shot, and recurring nightly jobs."),
            ("asks about volume of pending work or how far ahead",
             "Tens of thousands of pending jobs is plausible. Some sit for days."),
            ("asks about missed runs, clock, or many boxes",
             "If we were down at 02:00 the night job should still run when we come back. "
             "More than one box will run the scheduler."),
        ],
        discovery="Extracted one-shot + cron, pending volume, catch-up, and multi-box.",
        scoping="Designed due-work polling/partitioning that will not skip a missed cron.",
        stakeholders="Named the midnight herd and leader/lock problem.",
        communication="Defended due-time storage and catch-up from the doc.",
        ticket="Write implementation tickets for the scheduler",
    ),
    dict(
        key="iv_comments",
        title="Interview: nested comments",
        difficulty="junior",
        who=("yuki", "Yuki", "Staff interviewer"),
        problem=(
            "Design comments on a post: people reply to comments, we show a "
            "thread. Write the design. About twenty minutes."
        ),
        hidden_need=(
            "A few popular posts will have thousands of comments, we need "
            "pagination, and soft-delete (remove body, keep structure) is required."
        ),
        hidden_constraints=(
            "Nesting deeper than a few levels can flatten. Edits are allowed "
            "for a short window. No real-time typing in v1."
        ),
        rungs=[
            ("asks about volume per post or pagination",
             "Most posts are quiet. A few will have thousands of comments. We need pages, not one giant payload."),
            ("asks about delete, edit, or moderation",
             "Soft-delete: take the body down, keep the thread shape. Short edit window."),
            ("asks about nesting depth or real-time",
             "Deep trees can flatten after a few levels. Live typing is out of v1."),
        ],
        discovery="Got hot-post volume, pagination, soft-delete, and flatten-deep-threads.",
        scoping="Designed a thread model that can page and soft-delete.",
        stakeholders="Included moderation/delete, not only insert.",
        communication="Explained tree vs flat storage from their write-up.",
        ticket="Write implementation tickets for comments",
    ),
    dict(
        key="iv_calendar",
        title="Interview: meeting scheduler",
        difficulty="senior",
        who=("iris", "Iris", "Staff interviewer"),
        problem=(
            "Design a meeting scheduler: people have busy/free time, we find "
            "a slot, we book it. Twenty minutes to a written design."
        ),
        hidden_need=(
            "Tens of thousands of users, bookings must not double-book a person, "
            "and 'find a slot for N people this week' is the hard read."
        ),
        hidden_constraints=(
            "Time zones matter. External calendar sync is out of v1. A short "
            "hold/lock while someone confirms is expected so two people do not "
            "take the same slot."
        ),
        rungs=[
            ("asks about users, attendees, or the main action",
             "Tens of thousands of users. The painful call is 'find a slot for these N people this week'."),
            ("asks about double-booking or conflicts",
             "We must not double-book a person. Two people confirming at once is a real case."),
            ("asks about time zones or external calendars",
             "Time zones matter. Syncing Google/Outlook can wait."),
        ],
        discovery="Extracted scale, no double-book, N-person search, time zones, hold-on-confirm.",
        scoping="Designed availability + booking with a conflict story.",
        stakeholders="Treated scheduling as concurrency, not a date picker.",
        communication="Defended locking/holds and free-busy storage from the doc.",
        ticket="Write implementation tickets for the scheduler calendar",
    ),
    dict(
        key="iv_parking",
        title="Interview: parking garage occupancy",
        difficulty="mid",
        who=("sol", "Sol", "Staff interviewer"),
        problem=(
            "A garage wants a display and an API: how many spaces are free, "
            "and which floor. Design the system. Twenty minutes."
        ),
        hidden_need=(
            "A few hundred spaces, sensors are flaky, the display can be ~30s "
            "stale, and we need a daily occupancy report for the owner."
        ),
        hidden_constraints=(
            "Sensors double-count and drop events. Manual override for a stuck "
            "loop is required. No license-plate recognition in v1."
        ),
        rungs=[
            ("asks about size, floors, or how occupancy is sensed",
             "A few hundred spaces over a handful of floors. Loop sensors on the ramps — they are not perfect."),
            ("asks about freshness of the display or the API",
             "The lobby display can be half a minute behind. People are not racing F1."),
            ("asks about reports, accuracy, or what happens when sensors lie",
             "Owner wants a daily occupancy report. Sensors double-count and drop. Staff need a manual override."),
        ],
        discovery="Got scale, flaky sensors, 30s staleness, daily report, manual override.",
        scoping="Designed ingest → current occupancy → display/API with a correction path.",
        stakeholders="Designed for bad sensors, not a perfect counter.",
        communication="Explained reconciliation and override from their document.",
        ticket="Write implementation tickets for garage occupancy",
    ),
    dict(
        key="iv_tiny_analytics",
        title="Interview: tiny product analytics",
        difficulty="staff",
        who=("noor", "Noor", "Staff interviewer"),
        problem=(
            "Design a small analytics pipeline: our web app emits events "
            "(page view, click), we want funnels and a daily dashboard. "
            "Staff-level: I will expect you to cut scope. Twenty minutes."
        ),
        hidden_need=(
            "Tens of millions of events/day, dashboards are T+1 (next morning), "
            "and a few named funnels — not ad-hoc SQL for every PM."
        ),
        hidden_constraints=(
            "Client events will duplicate and arrive late. PII must not land "
            "in the warehouse. Real-time is explicitly out. Budget is one "
            "engineer plus existing object storage and a warehouse."
        ),
        rungs=[
            ("asks about volume, event types, or who consumes",
             "Tens of millions of events a day. Page views and clicks. A daily dashboard and a few named funnels."),
            ("asks about freshness or real-time",
             "Next morning is fine. Real-time is out of scope — please do not build it."),
            ("asks about late/duplicate events, PII, or budget",
             "Events duplicate and arrive late. Strip PII. One engineer, existing object store and warehouse."),
        ],
        discovery="Extracted daily volume, T+1, named funnels, late/dupes, PII, and no real-time.",
        scoping="Designed ingest → store → batch funnels with a v1 cut that a single engineer can run.",
        stakeholders="Showed what a pipeline must include (dedupe, privacy, batch vs stream).",
        communication="Defended the batch cut and event contract from their write-up.",
        ticket="Write implementation tickets for the analytics pipeline",
    ),
]


ASSESSOR = dict(
    key="rowan",
    name="Rowan",
    role="Staff assessor",
    voice="calm, precise, skeptical of buzzwords; asks about their document, not a textbook",
    lane="assessor",
    public_brief=(
        "You read the candidate's design and ask one probing question at a time "
        "about a decision they wrote. You are checking they made it and can "
        "defend it. You do not propose a better architecture. You do not reveal "
        "a model answer or hidden constraints they never extracted."
    ),
)


def _yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88)


def build(entry: dict) -> dict:
    key, name, role = entry["who"]
    problem = entry["problem"]
    return {
        "key": entry["key"],
        "title": entry["title"],
        "track": "interview",
        "role_label": "Candidate",
        "difficulty": entry["difficulty"],
        "starter_template": "starter",
        "definition_of_done": (
            "The candidate asks clarifying questions, writes a detailed understandable "
            "design, and defends that design under assessment. Extra credit: tickets "
            "an engineer could implement from."
        ),
        "world": {"facts": {
            "interview_length": "about 20 minutes from start to submitted design",
            "format": "clarifying questions, written design, then a defense",
            "rule": "the interviewer will not hand over the architecture",
        }},
        "personas": [
            {
                "key": key, "name": name, "role": role,
                "lane": "interviewer",
                "voice": "professional, concise, slightly busy; answers facts, not designs",
                "public_brief": problem,
                "hidden_need": entry["hidden_need"],
                "hidden_constraints": entry["hidden_constraints"],
                "reveal_ladder": [
                    {"unlock_when": u, "content": c} for u, c in entry["rungs"]
                ],
            },
            ASSESSOR,
        ],
        "triggers": [
            {
                "event_id": "problem_brief",
                "kind": "session_start",
                "at": 0,
                "min_level": "intern",
                "persona_key": key,
                "channel": f"dm:{key}",
                "content": problem,
            }
        ],
        "rubric": [
            {"key": "discovery", "weight": 2.0, "description": entry["discovery"]},
            {"key": "scoping", "weight": 2.0, "description": entry["scoping"]},
            {"key": "stakeholders", "weight": 1.0, "description": entry["stakeholders"]},
            {"key": "communication", "weight": 2.0, "description": entry["communication"]},
        ],
        "tickets": [
            {
                "title": entry["ticket"],
                "issue_type": "story",
                "priority": "medium",
                "labels": ["extra-credit", "implementation"],
                "created_by": "system",
                "status": "todo",
                "description": (
                    "## Extra credit\nWrite tickets so an engineer who has only "
                    "the tickets (not DESIGN.md) could implement this system.\n\n"
                    "## Acceptance criteria\n"
                    "- [ ] Each ticket has context, interface/data shape, and AC\n"
                    "- [ ] Together they cover the design you submitted\n"
                    "- [ ] An engineer would not need to guess a hidden component"
                ),
            }
        ],
    }


def write_starter(folder: Path, title: str) -> None:
    starter = folder / "starter"
    (starter / "docs").mkdir(parents=True, exist_ok=True)
    (starter / "src").mkdir(parents=True, exist_ok=True)
    (starter / "README.md").write_text(README_TMPL.format(title=title), encoding="utf-8")
    (starter / "DESIGN.md").write_text(DESIGN_MD.format(title=title), encoding="utf-8")
    (starter / "TICKETS.md").write_text(TICKETS_MD, encoding="utf-8")
    (starter / "docs" / "brief.md").write_text(BRIEF_TMPL, encoding="utf-8")
    (starter / "src" / "README.md").write_text(SRC_README, encoding="utf-8")


def main() -> None:
    assert len(SCENARIOS) == 20, len(SCENARIOS)
    for entry in SCENARIOS:
        folder = ROOT / entry["key"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "scenario.yaml").write_text(_yaml(build(entry)), encoding="utf-8")
        write_starter(folder, entry["title"])
        print("wrote", entry["key"])


if __name__ == "__main__":
    main()
