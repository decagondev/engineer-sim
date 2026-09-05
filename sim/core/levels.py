from __future__ import annotations

from dataclasses import dataclass, field

# Engineer levels, lowest to highest. Rank = index.
LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "principal",
               "distinguished"]


@dataclass(frozen=True)
class LevelProfile:
    key: str
    label: str
    beat_scale: float           # multiplies a trigger's turn threshold
    posture: str                # injected into persona prompts
    weight_shift: dict          # rubric criterion -> weight multiplier
    expectation: str            # note injected into the grader prompt

    @property
    def rank(self) -> int:
        return LEVEL_ORDER.index(self.key)


PROFILES: dict[str, LevelProfile] = {
    "intern": LevelProfile(
        "intern", "Intern", 1.8,
        "The engineer is an intern with little experience. Be patient and "
        "encouraging, explain your reasoning, and don't assume technical depth.",
        {"discovery": 1.4, "scoping": 0.7, "stakeholders": 0.6, "communication": 0.8},
        "Grade to intern expectations: reward uncovering the real need and sensible "
        "effort. Do not heavily penalise gaps in scoping or stakeholder polish."),
    "junior": LevelProfile(
        "junior", "Junior Engineer", 1.5,
        "The engineer is early-career. Be supportive but expect them to ask "
        "questions; explain when it helps.",
        {"discovery": 1.3, "scoping": 0.8, "stakeholders": 0.7, "communication": 0.9},
        "Grade to junior expectations: uncovering the need and a reasonable plan "
        "score well; polish is a bonus, not a requirement."),
    "mid": LevelProfile(
        "mid", "Mid-level Engineer", 1.2,
        "The engineer is a competent mid-level engineer. Be normal and "
        "professional; don't over-explain.",
        {}, "Grade to mid-level expectations: a solid, shippable outcome across the "
        "board is expected."),
    "senior": LevelProfile(
        "senior", "Senior Engineer", 1.0,
        "The engineer is senior. Be concise, assume solid judgement, and expect "
        "them to drive.",
        {"scoping": 1.1, "stakeholders": 1.1},
        "Grade to senior expectations: uncovering the need is expected; scoping and "
        "stakeholder handling should be strong."),
    "staff": LevelProfile(
        "staff", "Staff Engineer", 0.85,
        "The engineer is staff-level. Be terse, expect them to handle ambiguity "
        "and push back; don't hand-hold.",
        {"discovery": 0.85, "scoping": 1.2, "stakeholders": 1.3, "communication": 1.2},
        "Grade to staff expectations: uncovering the need is assumed. Score well "
        "only if scoping, stakeholder handling and communication are all strong."),
    "principal": LevelProfile(
        "principal", "Principal Engineer", 0.7,
        "The engineer is principal-level. Challenge their thinking and expect "
        "them to manage stakeholders and trade-offs proactively.",
        {"discovery": 0.8, "scoping": 1.3, "stakeholders": 1.4, "communication": 1.3},
        "Grade to principal expectations: leadership on scope, trade-offs and "
        "stakeholders is required; discovery alone is not enough."),
    "distinguished": LevelProfile(
        "distinguished", "Distinguished Engineer", 0.6,
        "The engineer is a distinguished engineer. Be demanding and skeptical; "
        "expect flawless scoping, stakeholder handling and communication.",
        {"discovery": 0.75, "scoping": 1.4, "stakeholders": 1.5, "communication": 1.4},
        "Grade to distinguished expectations: only near-flawless scoping, "
        "stakeholder management and communication score well."),
}

DEFAULT_LEVEL = "senior"


def rank(level: str) -> int:
    return LEVEL_ORDER.index(level) if level in LEVEL_ORDER else rank(DEFAULT_LEVEL)


def profile(level: str) -> LevelProfile:
    return PROFILES.get(level, PROFILES[DEFAULT_LEVEL])


def levels_meta() -> list[dict]:
    return [{"key": k, "label": PROFILES[k].label, "rank": i}
            for i, k in enumerate(LEVEL_ORDER)]


def systems_posture(level: str) -> str:
    """Persona posture when the trainee is in the Systems Designer seat."""
    return (
        profile(level).posture + " "
        "This is a system-design review, not a feature ticket. The engineer is "
        "proposing an architecture. Push on scale, failure modes, data consistency, "
        "operational cost, and what they would explicitly not build in v1. Ask one "
        "hard question at a time. You may write a short paragraph when challenging "
        "a trade-off. Do not accept a box diagram without numbers or a bottleneck."
    )


def systems_expectation(level: str) -> str:
    return (
        profile(level).expectation + " "
        "This is a system-design engagement. Reward a defended architecture: "
        "named requirements, capacity numbers, failure modes, trade-offs, and a "
        "clear v1 cut-line. Penalise buzzword diagrams and an undefended happy path."
    )


def interview_posture(level: str, lane: str = "interviewer") -> str:
    """Persona posture for interview-style assessment scenarios."""
    base = profile(level).posture
    if lane == "assessor":
        return (
            base + " "
            "You are the ASSESSOR in a system-design interview. You have the "
            "student's own design document. Ask one probing question at a time "
            "about a specific decision THEY wrote. Verify they authored it and "
            "can defend it. Test problem-solving and whether they understand "
            "what a system design includes (API, data, scale, failure, v1 cut). "
            "Do not propose a better architecture. Do not teach the 'correct' "
            "answer. Do not invent components they did not mention. Do not leak "
            "hidden constraints they never extracted. If they are vague, ask "
            "them to point at their own document."
        )
    return (
        base + " "
        "You are the INTERVIEWER in a timed system-design interview. Present "
        "the problem; then answer clarifying questions with concise facts from "
        "what you have been given — the way a real interviewer would. Never "
        "outline the architecture. Never volunteer a component, cache, queue, "
        "or 'have you considered…'. Never leak locked constraints. If they ask "
        "something you do not have, say you do not have that number or that it "
        "is their call. Keep answers short. Do not grade them in chat."
    )


def interview_expectation(level: str) -> str:
    return (
        "INTERVIEW ASSESSMENT. " + profile(level).expectation + " "
        "Grade from (1) clarifying questions in the transcript — did they "
        "extract the real constraints without being fed the answer; "
        "(2) the submitted design document — detail, correctness, and whether "
        "a staff engineer could understand it; (3) whether they treated this as "
        "a real system design (API, data, scale, consistency, failure, v1 cut); "
        "(4) assessment Q&A — do they understand and defend THEIR design. "
        "This is less about matching a canonical architecture and more about "
        "understanding the problem and defending decisions. Do not reward a "
        "plausible design they cannot explain. A defensible alternate is fine. "
        "If a tickets criterion is present, that portion is extra credit: "
        "could an engineer implement from the tickets alone?"
    )
