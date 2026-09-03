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
