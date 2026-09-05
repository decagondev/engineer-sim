from __future__ import annotations

from dataclasses import dataclass, field

from sim.core.persona.persona import Persona, RevealRung
from sim.core.world.world_state import WorldState


class ScenarioError(ValueError):
    """Raised when a scenario definition is invalid."""


def _labels(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        return ",".join(str(x).strip() for x in raw if str(x).strip())
    return ",".join(p.strip() for p in str(raw).split(",") if p.strip())


@dataclass(frozen=True)
class TriggerSpec:
    """Declarative trigger + event (parsed by the director in Wave 2)."""

    event_id: str
    kind: str                    # trigger kind, e.g. "turn_count"
    at: int                      # threshold for turn_count
    persona_key: str
    channel: str
    content: str
    action: str = "chat"         # "chat" | "email" | "ticket"
    subject: str = ""
    min_level: str = "intern"    # beat only fires at/above this engineer level
    issue_type: str = ""         # ticket metadata
    priority: str = ""
    labels: str = ""


@dataclass(frozen=True)
class Scenario:
    """A scenario is DATA: personas + world + triggers + rubric. New scenarios
    are new files, not code (Open/Closed). Parsing lives here (pure).
    """

    key: str
    title: str
    world: WorldState
    personas: tuple[Persona, ...]
    triggers: tuple[TriggerSpec, ...] = field(default_factory=tuple)
    rubric: tuple = field(default_factory=tuple)          # parsed in Wave 3
    definition_of_done: str = ""
    difficulty: str = "mid"                               # level this scenario is pitched at
    starter_template: str = ""                            # path to starter repo (Wave 5)
    image: str = ""                                       # docker image override (optional)
    tickets: tuple = field(default_factory=tuple)         # seed tickets (Wave 7)
    track: str = "product"                                # product | systems | interview
    role_label: str = ""                                  # e.g. Systems Designer / Candidate

    @property
    def primary_persona(self) -> Persona:
        return self.personas[0]

    @property
    def cast(self) -> dict[str, Persona]:
        return {p.key: p for p in self.personas}

    @staticmethod
    def from_dict(data: dict) -> "Scenario":
        try:
            key, title = data["key"], data["title"]
        except KeyError as e:
            raise ScenarioError(f"scenario missing required field: {e}") from e

        world = WorldState(facts=dict(data.get("world", {}).get("facts", {})))

        raw_personas = data.get("personas", [])
        if not raw_personas:
            raise ScenarioError("scenario must define at least one persona")

        personas = []
        for p in raw_personas:
            try:
                ladder = tuple(
                    RevealRung(unlock_when=r["unlock_when"], content=r["content"])
                    for r in p.get("reveal_ladder", [])
                )
                personas.append(Persona(
                    key=p["key"], name=p["name"], role=p["role"], voice=p["voice"],
                    public_brief=p["public_brief"],
                    hidden_need=p.get("hidden_need", ""),
                    hidden_constraints=p.get("hidden_constraints", ""),
                    reveal_ladder=ladder,
                    lane=p.get("lane", "") or "",
                ))
            except KeyError as e:
                raise ScenarioError(f"persona missing required field: {e}") from e

        triggers = tuple(
            TriggerSpec(
                event_id=t["event_id"], kind=t.get("kind", "turn_count"),
                at=int(t.get("at", 0)), persona_key=t["persona_key"],
                channel=t.get("channel", "general"), content=t["content"],
                action=t.get("action", "chat"), subject=t.get("subject", ""),
                min_level=t.get("min_level", "intern"),
                issue_type=t.get("issue_type", ""),
                priority=t.get("priority", ""),
                labels=_labels(t.get("labels", "")),
            )
            for t in data.get("triggers", [])
        )

        from sim.core.grading.rubric import Rubric  # local import: avoid cycle
        rubric = Rubric.from_list(data.get("rubric", []))

        return Scenario(
            key=key, title=title, world=world, personas=tuple(personas),
            triggers=triggers, rubric=rubric,
            definition_of_done=data.get("definition_of_done", ""),
            difficulty=data.get("difficulty", "mid"),
            starter_template=data.get("starter_template", ""),
            image=data.get("image", ""),
            tickets=tuple(data.get("tickets", [])),
            track=data.get("track", "product") or "product",
            role_label=data.get("role_label", "") or (
                "Systems Designer" if data.get("track") == "systems"
                else "Candidate" if data.get("track") == "interview"
                else "Engineer"
            ),
        )
