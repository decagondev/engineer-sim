# Design: home feed

Author: (you)
Status: draft
Reviewers: Ansel (VP Eng), Oren (SRE/data)

## 1. Problem

## 2. Requirements / non-goals
Ads: in or out, one sentence Ansel can repeat.

## 3. Scale
| Signal | Order of magnitude | Source |
| --- | --- | --- |
| MAU | ~50M | given |
| Max followers (celebrity) |  |  |
| p99 friends |  |  |

## 4. Fan-out stance
Write / read / hybrid. Rule for celebrities.

```
publish -> ?
read    -> ?
```

## 5. Freshness SLO
The number you will put on a slide.

## 6. Ranking (v1)
How dumb is acceptable?

## 7. Incidents
Friend graph stale. Celebrity post during a deploy.

## 8. v1 cut-line
