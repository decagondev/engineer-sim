# Design: per-tenant API limits

Author: (you)
Status: draft
Reviewers: Kiran (EM), Moe (SRE), Tess (Sales)

## 1. Problem
<!-- Noisy neighbour vs paid burst vs "unlimited" logo. -->

## 2. Requirements / non-goals

## 3. Tenant classes
| Class | Limit shape | Who owns exceptions |
| --- | --- | --- |
| Free |  |  |
| Enterprise |  |  |
| Unlimited (named) |  |  |

## 4. Algorithm
Why this and not nginx `limit_req`.

## 5. Counter placement
us-east vs eu. What "eventual" means for a dual-region burst.

## 6. Client contract
429 body, headers, retry-after. What we never leak.

## 7. Fail open vs fail closed
One sentence for the CEO. Kill switch.

## 8. v1 cut-line
