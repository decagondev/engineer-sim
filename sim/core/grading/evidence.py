"""Point a grade's evidence back at the transcript message it quotes. Pure.

The grader cites evidence in prose that usually paraphrases a message. `locate`
picks the message whose content matches best: an exact case-insensitive quote
first, otherwise the message sharing the most distinctive words with the
evidence, provided the overlap is convincing (MIN_SHARED words and MIN_RATIO of
the evidence's distinctive words). Events are never cited.
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

MIN_SHARED = 2
MIN_RATIO = 0.5
_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("""
a an the and or but if then so of to in on at for by with from as is are was were be
been being do does did done has have had having it its this that these those they
them their there here what which who whom how when where why will would can could
should may might must not no yes about into over under up down out off again more
most very just also than too only own same such i you he she we me him her us my
your his our candidate asked ask asks asking said says say""".split())


def _norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _tokens(text: str) -> set:
    return {_stem(w) for w in _WORD.findall((text or "").lower())
            if len(w) >= 3 and w not in _STOP}


def locate(evidence: str, rows: Sequence[object]) -> Optional[int]:
    """Id of the message the evidence quotes, or None. Rows are StoredMessage-
    like objects with `id`, `kind`, `content`."""
    ev = _norm(evidence)
    if len(ev) < 8:
        return None
    candidates = [r for r in rows if getattr(r, "kind", "message") == "message"
                  and getattr(r, "id", None) is not None]
    for r in candidates:                       # exact quote inside a message
        if ev in _norm(getattr(r, "content", "")):
            return r.id
    for r in candidates:                       # short message quoted inside the evidence
        c = _norm(getattr(r, "content", ""))
        if len(c) >= 16 and c in ev:
            return r.id
    ev_tokens = _tokens(evidence)
    if len(ev_tokens) < MIN_SHARED:
        return None
    best_id, best_score, best_shared = None, 0.0, 0
    for r in candidates:
        shared = len(ev_tokens & _tokens(getattr(r, "content", "")))
        score = shared / len(ev_tokens)
        if shared > best_shared or (shared == best_shared and score > best_score):
            best_id, best_score, best_shared = r.id, score, shared
    if best_shared >= MIN_SHARED and best_score >= MIN_RATIO:
        return best_id
    return None


def annotate(grade: dict, rows: Sequence[object]) -> dict:
    """Return a copy of the grade body with `evidence_ref` on every score."""
    body = dict(grade or {})
    out = []
    for s in body.get("scores", []):
        s = dict(s)
        s["evidence_ref"] = locate(s.get("evidence", ""), rows)
        out.append(s)
    body["scores"] = out
    extra = body.get("tickets_extra")
    if extra:
        extra = dict(extra)
        extra["evidence_ref"] = locate(extra.get("evidence", ""), rows)
        body["tickets_extra"] = extra
    return body
