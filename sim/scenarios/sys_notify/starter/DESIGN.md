# Design: notifications service

Author: (you)
Status: draft
Reviewers: Evan (EM), Sasha (SRE)

## 1. Problem

## 2. Requirements
Must / Should / Non-goals (v1):

## 3. Event contract
<!-- Who publishes? What is the idempotency key? Transactional vs marketing. -->

## 4. Architecture
```
producer -> ? -> workers -> channel adapters
```

## 5. Channels and providers
| Channel | Provider now | v1? | Notes |
| --- | --- | --- | --- |
| Email | Sendgrid |  |  |
| Push | FCM |  |  |
| SMS |  |  |  |
| In-app inbox |  |  |  |

## 6. Failure modes
| Failure | User sees | What we do |
| --- | --- | --- |
| Provider 500 for 20 min |  |  |
| Duplicate checkout.paid |  |  |

## 7. Quiet hours, opt-out, delete

## 8. v1 cut-line

## 9. Open questions
