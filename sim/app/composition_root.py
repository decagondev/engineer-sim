from __future__ import annotations

from sim.app.config import Config
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import TurnCountTrigger
from sim.core.grading.grader import LLMGrader
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.ports.llm import LLMClient
from sim.core.scenario.scenario import Scenario
from sim.core.session.session_service import SessionService

# The ONLY place adapters meet the core. Everything is wired here.

_DEMO_SCENARIO = {
    "key": "churn_dashboard",
    "title": "The dashboard that isn't really about dashboards",
    "difficulty": "mid",
    "starter_template": "STARTER_PLACEHOLDER",
    "definition_of_done": (
        "The engineer uncovers that Priya needs proactive churn early-warning "
        "(not just charts), scopes something shippable within the constraints, "
        "and communicates a plan back to the stakeholders."
    ),
    "world": {"facts": {
        "deadline": "end of the quarter (about 6 weeks)",
        "budget": "one engineer, part-time",
        "team": "a 40-person B2B SaaS company",
    }},
    "personas": [
        {
            "key": "priya",
            "name": "Priya",
            "role": "Head of Customer Success",
            "voice": "warm but busy; talks in outcomes, not tech; slightly vague",
            "public_brief": (
                "You want 'a dashboard' showing how customers are doing. You "
                "mention charts and maybe a weekly email."
            ),
            "hidden_need": (
                "Early warning of which accounts are about to churn so your team "
                "can intervene in time. A dashboard nobody checks won't help."
            ),
            "hidden_constraints": (
                "Data is messy, split across Stripe and a Postgres DB. No new "
                "headcount. Anything needing daily manual work will die."
            ),
            "reveal_ladder": [
                {"unlock_when": "asks what decision or action the tool should "
                                "drive, or who uses it and when",
                 "content": "Your team is reactive — you only hear about unhappy "
                            "accounts once they've already given notice."},
                {"unlock_when": "asks about data sources or where the numbers "
                                "live",
                 "content": "Usage data is in the product's Postgres DB; billing "
                            "and plan changes are in Stripe; they don't join up."},
                {"unlock_when": "asks what 'doing well' or 'at risk' actually "
                                "means in measurable terms",
                 "content": "At-risk really means: usage dropping week over week, "
                            "or a downgrade, or support tickets spiking."},
            ],
        },
        {
            "key": "dana",
            "name": "Dana",
            "role": "Finance Business Partner",
            "voice": "polite, precise, cost-conscious; writes in email",
            "public_brief": (
                "You care that whatever gets built has no new licence or tooling "
                "cost and needs no extra headcount. You ask for confirmation in writing."
            ),
            "reveal_ladder": [],
        },
        {
            "key": "marcus",
            "name": "Marcus",
            "role": "VP of Engineering (the uninvited stakeholder)",
            "voice": "blunt, time-pressed, worried about scope and maintenance",
            "public_brief": (
                "You drop in to check the plan is realistic for one part-time "
                "engineer and won't become a maintenance burden. You push on "
                "scope."
            ),
            "reveal_ladder": [],
        },
    ],
    "triggers": [
        {"event_id": "priya_scope_ticket", "kind": "turn_count", "at": 4,
         "action": "ticket", "persona_key": "priya", "channel": "dm:priya",
         "min_level": "mid",
         "subject": "Can it also show a revenue chart?",
         "content": "Oh — while you are at it, could the tool also show a "
                    "revenue-over-time chart on the same screen? The exec team "
                    "would love that."},
        {"event_id": "dana_email", "kind": "turn_count", "at": 5,
         "action": "email", "persona_key": "dana", "channel": "general",
         "min_level": "senior",
         "subject": "Budget for the CS tooling work",
         "content": "Hi — Finance here. We are trimming Q3 discretionary spend, so "
                    "whatever you build needs to run on existing infrastructure with no "
                    "new licences or tooling cost, and no extra headcount. Could you "
                    "confirm in a reply that the approach fits within that? Thanks, Dana"},
        {"event_id": "marcus_appears", "kind": "turn_count", "at": 3,
         "persona_key": "marcus", "channel": "dm:marcus",
         "min_level": "intern",
         "content": "Marcus here — saw this thread. Before you build anything, "
                    "how big is this? We can't take on another thing that needs "
                    "babysitting every day."},
    ],
    "tickets": [
        {"title": "Build a customer health dashboard",
         "description": "Priya's original request: charts of how customers are doing, plus maybe a weekly email.", "created_by": "priya", "status": "todo"},
        {"title": "Figure out what 'at risk' actually means",
         "description": "Placeholder — the real definition needs to come out of discovery.", "created_by": "system", "status": "todo"},
    ],
    "rubric": [
        {"key": "discovery", "weight": 2.0,
         "description": "Uncovered the real need (churn early-warning) rather "
                        "than building the literal dashboard that was asked for."},
        {"key": "scoping", "weight": 1.5,
         "description": "Scoped something shippable within the deadline, budget, "
                        "and data constraints."},
        {"key": "stakeholders", "weight": 1.0,
         "description": "Handled Marcus's scope/maintenance concerns credibly."},
        {"key": "communication", "weight": 1.0,
         "description": "Explained the plan clearly back to non-technical "
                        "stakeholders."},
    ],
}


def build_llm(config: Config) -> LLMClient:
    provider = config.llm_provider.lower()
    if provider == "fake":
        from sim.adapters.llm.fake_client import FakeLLMClient
        return FakeLLMClient()
    if provider == "ollama":
        from sim.adapters.llm.ollama_client import OllamaClient
        return OllamaClient(model=config.ollama_model)
    if provider == "anthropic":
        from sim.adapters.llm.anthropic_client import AnthropicClient
        return AnthropicClient(model=config.anthropic_model)
    raise ValueError(f"unknown LLM_PROVIDER: {config.llm_provider!r}")


def build_registry(config: Config) -> dict:
    """All available scenarios, keyed by scenario.key (loaded from YAML files)."""
    from pathlib import Path
    from sim.adapters.persistence.scenario_files import load_scenario_file
    reg = {}
    base = Path(__file__).resolve().parents[1] / "scenarios"
    for yml in sorted(base.glob("*/scenario.yaml")):
        sc = load_scenario_file(yml)
        reg[sc.key] = sc
    if not reg:
        demo = build_scenario(config)
        reg[demo.key] = demo
    return reg


def build_manager(config: Config, llm=None, judge_llm=None):
    from sim.app.manager import SessionManager
    registry = build_registry(config)
    default_key = "churn_dashboard" if "churn_dashboard" in registry else next(iter(registry))
    return SessionManager(config, registry, default_key,
                          llm or build_llm(config), judge_llm or build_llm(config))


def build_scenario(config: Config) -> Scenario:
    if config.scenario_path:
        from sim.adapters.persistence.scenario_files import load_scenario_file
        return load_scenario_file(config.scenario_path)
    import dataclasses
    from pathlib import Path
    scenario = Scenario.from_dict(_DEMO_SCENARIO)
    if scenario.starter_template == "STARTER_PLACEHOLDER":
        starter = (Path(__file__).resolve().parents[1]
                   / "scenarios" / "churn_dashboard" / "starter")
        scenario = dataclasses.replace(scenario, starter_template=str(starter))
    return scenario


def build_director(scenario: Scenario) -> Director | None:
    rules = []
    for t in scenario.triggers:
        if t.kind == "turn_count":
            rules.append((
                TurnCountTrigger(at=t.at, min_level=t.min_level),
                Event(event_id=t.event_id, persona_key=t.persona_key,
                      channel=t.channel, content=t.content,
                      kind=t.action, subject=t.subject),
            ))
    return Director(rules) if rules else None


def build_environment(config: Config, scenario: Scenario):
    if config.env_provider == "local_folder":
        from sim.adapters.environment.local_folder import LocalFolderEnvironment
        return LocalFolderEnvironment(root=config.sandbox_root,
                                      starter_template=scenario.starter_template)
    if config.env_provider == "docker":
        from sim.adapters.environment.docker import DockerEnvironment
        image = scenario.image or config.sandbox_image
        return DockerEnvironment(
            root=config.sandbox_root, starter_template=scenario.starter_template,
            image=image, memory=config.sandbox_memory, cpus=config.sandbox_cpus,
            pids=config.sandbox_pids)
    raise ValueError(f"unknown ENV_PROVIDER: {config.env_provider!r}")


def build_grader(config: Config) -> LLMGrader:
    return LLMGrader(build_llm(config))


def build_session_service(
    config: Config,
    llm: LLMClient | None = None,
    judge_llm: LLMClient | None = None,
    scenario: Scenario | None = None,
) -> SessionService:
    from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository
    from sim.adapters.persistence.sqlite_state import SqliteUnlockStore
    from sim.adapters.persistence.sqlite_mail import SqliteMailStore
    from sim.adapters.persistence.sqlite_tickets import SqliteTicketStore
    from sim.adapters.persistence.sqlite_settings import SqliteSettingsStore
    from sim.core.mail.mail_service import MailService
    from sim.core.tickets.ticket_service import TicketService

    scenario = scenario or build_scenario(config)
    repo = SqliteMessageRepository(config.db_path)
    unlock = SqliteUnlockStore(config.db_path)
    settings = SqliteSettingsStore(config.db_path)
    responder = PersonaResponder(llm or build_llm(config))
    mail = MailService(
        writer=repo, reader=repo, mail_store=SqliteMailStore(config.db_path),
        responder=responder, unlock_store=unlock,
        world=scenario.world, cast=scenario.cast, settings=settings)
    tickets = TicketService(
        store=SqliteTicketStore(config.db_path), writer=repo,
        cast=scenario.cast, seed_tickets=scenario.tickets)
    svc = SessionService(
        writer=repo, reader=repo, responder=responder,
        unlock_store=unlock,
        unlock_evaluator=UnlockEvaluator(judge_llm or build_llm(config)),
        world=scenario.world, cast=scenario.cast,
        director=build_director(scenario), mail_service=mail,
        ticket_service=tickets, settings=settings,
        primary_key=scenario.primary_persona.key,
    )
    svc.settings_store = settings   # exposed for the web layer
    return svc


def _build_workspace_reader():
    from sim.adapters.workspace.local_reader import LocalWorkspaceReader
    return LocalWorkspaceReader()


def build_app(config: Config | None = None):
    from sim.adapters.web.app import create_web_app
    from sim.adapters.build.git_observer import GitBuildObserver
    config = config or Config.from_env()
    manager = build_manager(config)
    return create_web_app(
        manager=manager,
        grader=build_grader(config),
        grader_calibrated=config.grader_calibrated,
        build_observer=GitBuildObserver(),
        workspace_reader=_build_workspace_reader(),
        instructor_password=config.instructor_password,
    )
