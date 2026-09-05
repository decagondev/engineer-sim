# Design: live presence and cursors

Author: (you)
Status: draft
Reviewers: Jules (EM), Rei (Staff), Dana (Finance)

## 1. Problem
<!-- Demo vs production. Presence vs full text sync. -->

## 2. Requirements / non-goals

## 3. Load
| Signal | Demo | Whale workspace | Source |
| --- | --- | --- | --- |
| People on one doc | 8 |  |  |
| Open docs | 1 |  |  |

## 4. Architecture
```
client <-> gateway <-> room / presence store
```

## 5. Presence
Heartbeat, expiry, ghosts after laptop sleep.

## 6. Fan-out
Who receives a cursor move? How do we not broadcast company-wide?

## 7. Failure
Websocket box bounce mid-demo. Reconnect / resume.

## 8. Vendors
Why this is not Pusher/Ably (or why you are asking Dana to reopen that).

## 9. v1 cut-line
