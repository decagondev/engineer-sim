# Design: first-party short links

Author: (you)
Status: draft
Reviewers: Nia (EM), Cole (SRE)

## 1. Problem
<!-- What are we actually building, in one paragraph? -->

## 2. Requirements
Must:
- 

Should:
- 

Non-goals (v1):
- 

## 3. Load and SLOs
<!-- QPS / daily redirects, p99 redirect latency, data durability. Ranges are fine. -->

| Signal | v1 target | How we know |
| --- | --- | --- |
| Redirects / day |  |  |
| p99 redirect |  |  |
| Click count freshness |  |  |

## 4. High-level design
<!-- Create-link path and redirect path. Name the store and the cache. -->

```
client -> ? -> ?
```

## 5. Data
<!-- ID scheme, collision handling, what is stored per link. -->

## 6. Failure modes
| Failure | User sees | What we do |
| --- | --- | --- |
| Cache empty |  |  |
| Postgres slow |  |  |

## 7. v1 cut-line
In:
- 

Out (and why):
- 

## 8. Open questions
- 
