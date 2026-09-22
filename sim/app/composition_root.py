from __future__ import annotations

from sim.app.config import Config
from sim.core.director.director import Director
from sim.core.director.events import Event
from sim.core.director.triggers import (
    SessionStartTrigger, SubmissionTrigger, TurnCountTrigger)
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
         "issue_type": "story", "priority": "high", "labels": ["scope-creep", "exec"],
         "subject": "Can it also show a revenue chart?",
         "content": "## Request\nAdd a revenue-over-time chart on the same screen "
                    "as account health.\n\n## Why now\nThe exec team asked Priya; "
                    "she's passing it along mid-thread.\n\n## Acceptance criteria\n"
                    "- [ ] Revenue over time visible alongside health\n"
                    "- [ ] Uses existing Stripe billing data\n\n"
                    "## Risk\nLikely scope creep. Confirm with Engineering before committing."},
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
         "description": (
             "## Context\nCustomer Success wants visibility into how accounts "
             "are doing. Priya asked for a dashboard and possibly a weekly email.\n\n"
             "## Acceptance criteria\n- [ ] CS can see current health for accounts they own\n"
             "- [ ] A weekly digest can be sent from the same data\n"
             "- [ ] Uses existing Stripe + Postgres (no new vendors)\n\n"
             "## Notes\nDefinition of 'healthy' is still TBD — talk to Priya before building."
         ),
         "created_by": "priya", "status": "todo",
         "issue_type": "story", "priority": "high", "labels": ["cs", "dashboard"]},
        {"title": "Figure out what 'at risk' actually means",
         "description": (
             "## Why\nWe cannot ship a health view until 'at risk' is measurable.\n\n"
             "## Outcome\nA short written definition Priya agrees on, with signals we can compute.\n\n"
             "## Acceptance criteria\n- [ ] Definition agreed with CS\n"
             "- [ ] Each signal has a named data source"
         ),
         "created_by": "system", "status": "todo",
         "issue_type": "spike", "priority": "high", "labels": ["discovery"]},
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
    """The primary provider, wrapped in a failover chain when
    LLM_FALLBACK_PROVIDERS names others to try on rate limits or outages."""
    import dataclasses
    primary = _build_single_llm(config)
    names = [p.strip().lower() for p in (config.llm_fallback_providers or "").split(",") if p.strip()]
    names = [n for n in names if n != config.llm_provider.lower()]
    if not names:
        return primary
    from sim.adapters.llm.failover import FailoverLLMClient
    fallbacks = []
    for n in names:
        try:
            fallbacks.append((n, _build_single_llm(dataclasses.replace(config, llm_provider=n))))
        except Exception:
            continue
    return FailoverLLMClient(primary, fallbacks, primary_name=config.llm_provider.lower())


def _build_single_llm(config: Config) -> LLMClient:
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
    if provider == "groq":
        from sim.adapters.llm.groq_client import GroqClient
        return GroqClient(model=config.groq_model)
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


def build_manager(config: Config, llm=None, judge_llm=None, repo_files=None):
    from sim.app.manager import SessionManager
    registry = build_registry(config)
    default_key = "churn_dashboard" if "churn_dashboard" in registry else next(iter(registry))
    return SessionManager(config, registry, default_key,
                          llm or build_llm(config), judge_llm or build_llm(config),
                          repo_files=repo_files)


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
            trigger = TurnCountTrigger(at=t.at, min_level=t.min_level)
        elif t.kind == "submission":
            trigger = SubmissionTrigger(at=t.at or 1, min_level=t.min_level)
        elif t.kind == "session_start":
            trigger = SessionStartTrigger(min_level=t.min_level)
        else:
            continue
        rules.append((
            trigger,
            Event(event_id=t.event_id, persona_key=t.persona_key,
                  channel=t.channel, content=t.content,
                  kind=t.action, subject=t.subject,
                  issue_type=t.issue_type, priority=t.priority,
                  labels=t.labels),
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


def build_grader(config: Config, users=None) -> LLMGrader:
    llm = build_llm(config)
    if users is not None:
        from sim.adapters.llm.scoped_client import wrap_user_scoped_llm
        llm = wrap_user_scoped_llm(llm, users=users, config=config)
    return LLMGrader(llm)


def build_session_service(
    config: Config,
    llm: LLMClient | None = None,
    judge_llm: LLMClient | None = None,
    scenario: Scenario | None = None,
) -> SessionService:
    from sim.adapters.persistence.stores import build_stores
    from sim.core.mail.mail_service import MailService
    from sim.core.tickets.ticket_service import TicketService, project_prefix

    scenario = scenario or build_scenario(config)
    stores = build_stores(config)
    repo = stores.repo
    unlock = stores.unlock
    settings = stores.settings
    responder = PersonaResponder(llm or build_llm(config))
    mail = MailService(
        writer=repo, reader=repo, mail_store=stores.mailstore,
        responder=responder, unlock_store=unlock,
        world=scenario.world, cast=scenario.cast, settings=settings)
    tickets = TicketService(
        store=stores.ticketstore, writer=repo,
        cast=scenario.cast, seed_tickets=scenario.tickets,
        project_key=project_prefix(scenario.key))
    svc = SessionService(
        writer=repo, reader=repo, responder=responder,
        unlock_store=unlock,
        unlock_evaluator=UnlockEvaluator(judge_llm or build_llm(config)),
        world=scenario.world, cast=scenario.cast,
        director=build_director(scenario), mail_service=mail,
        ticket_service=tickets, settings=settings,
        primary_key=scenario.primary_persona.key,
        track=scenario.track, role_label=scenario.role_label,
    )
    svc.settings_store = settings   # exposed for the web layer
    return svc


def _build_workspace_reader():
    from sim.adapters.workspace.local_reader import LocalWorkspaceReader
    return LocalWorkspaceReader()


def build_auth(config: Config, manager) -> "object":
    """Wire identity adapters. Core never sees Firebase."""
    from sim.adapters.auth.services import AuthServices
    from sim.adapters.auth.fake_verifier import FakeVerifier
    users = getattr(manager, "users", None)
    sessions = getattr(manager, "session_registry", None)
    mode = (config.auth_mode or "password").lower()
    if mode == "firebase":
        if not config.firebase_web_api_key or not config.firebase_project_id:
            raise RuntimeError(
                "AUTH_MODE=firebase requires FIREBASE_WEB_API_KEY and "
                "FIREBASE_PROJECT_ID")
        from sim.adapters.auth.firebase_verifier import FirebaseVerifier
        fb = FirebaseVerifier(
            config.firebase_web_api_key, config.firebase_project_id,
            credentials_json=config.firebase_credentials_json)
        return AuthServices(
            "firebase", verifier=fb, users=users, sessions=sessions,
            bootstrap_admin_email=config.bootstrap_admin_email,
            firebase_api_key=config.firebase_web_api_key,
            firebase_auth_domain=config.firebase_auth_domain
            or f"{config.firebase_project_id}.firebaseapp.com",
            firebase_project_id=config.firebase_project_id,
            firebase=fb,
        )
    if mode == "fake":
        return AuthServices(
            "fake", verifier=FakeVerifier(), users=users, sessions=sessions,
            bootstrap_admin_email=config.bootstrap_admin_email,
        )
    return AuthServices(
        "password", password=config.instructor_password,
        users=users, sessions=sessions,
    )


def build_app(config: Config | None = None):
    from sim.adapters.web.app import create_web_app
    from sim.adapters.build.git_observer import GitBuildObserver
    from sim.adapters.build.github_observer import GitHostBuildObserver
    from sim.adapters.workspace.github_files import RepoWorkspaceFiles
    config = config or Config.from_env()
    manager = build_manager(config)
    # One router over every configured forge (GitHub always; a GitLab instance
    # when GITLAB_URL is set). Reads use the signed-in user's own token when
    # they stored one (Settings / Connect), else the classroom token.
    hosts, gitlab_oauth = _build_repo_hosts(config, manager.users)
    github = GitHostBuildObserver(host=hosts)
    manager.repo_files = github
    return create_web_app(
        manager=manager,
        grader=build_grader(config, users=manager.users),
        grader_calibrated=config.grader_calibrated,
        build_observer=GitBuildObserver(),
        workspace_reader=_build_workspace_reader(),
        instructor_password=config.instructor_password,
        github_observer=github,
        auth=build_auth(config, manager),
        public_base_url=config.public_base_url,
        hosted=config.hosted,
        repo_files=RepoWorkspaceFiles(host=hosts, can_write=hosts.can_write),
        github_oauth=_build_github_oauth(config),
        gitlab_oauth=gitlab_oauth,
    )


def _build_repo_hosts(config: Config, users):
    """HostRouter over GitHub (+ a GitLab instance when configured) and the
    GitLab device-flow broker (None when no GITLAB_URL)."""
    from sim.adapters.auth.secretbox import secret_from_config
    from sim.adapters.build.github_api import GitHubApi, user_token_resolver
    from sim.adapters.build.github_host import GitHubHost
    from sim.adapters.build.host_router import HostRouter
    secret = secret_from_config(config)
    github = GitHubHost(api=GitHubApi(token=config.github_token, resolve_token=user_token_resolver(
        users, secret, config.github_token)))
    hosts = [github]
    can_write = {github.host: _github_can_write(users)}
    gitlab_oauth = None
    if config.gitlab_url:
        from sim.adapters.auth.gitlab_oauth import GitLabDeviceFlow
        from sim.adapters.auth.gitlab_tokens import user_token_resolver as gitlab_resolver
        from sim.adapters.build.gitlab_api import GitLabHost
        gitlab_oauth = GitLabDeviceFlow(config.gitlab_url, config.gitlab_oauth_client_id)
        gitlab = GitLabHost(config.gitlab_url, resolve_token=gitlab_resolver(
            users, secret, config.gitlab_token, broker=gitlab_oauth))
        hosts.append(gitlab)
        can_write[gitlab.host] = _gitlab_can_write(users)
    return HostRouter(hosts, can_write), gitlab_oauth


def _gitlab_can_write(users):
    """True when the current request's user connected GitLab with the `api`
    scope (the only scope that lets the REST file API commit)."""
    def can_write() -> bool:
        from sim.adapters.llm.request_context import current_uid
        uid = current_uid.get()
        if not uid or users is None:
            return False
        rec = users.get(uid)
        scope = (getattr(rec, "gitlab_scope", "") or "") if rec else ""
        return bool(getattr(rec, "gitlab_token_enc", "")) and "api" in scope.replace(",", " ").split()
    return can_write


def _github_can_write(users):
    """True when the current request's user connected GitHub with a scope that
    allows commits (public_repo or repo). Pasted read-only tokens never write."""
    def can_write() -> bool:
        from sim.adapters.llm.request_context import current_uid
        uid = current_uid.get()
        if not uid or users is None:
            return False
        rec = users.get(uid)
        scope = (getattr(rec, "github_scope", "") or "") if rec else ""
        return bool(getattr(rec, "github_token_enc", "")) and any(
            s in ("public_repo", "repo") for s in scope.replace(",", " ").split())
    return can_write


def _build_github_oauth(config: Config):
    from sim.adapters.auth.github_oauth import GitHubDeviceFlow
    return GitHubDeviceFlow(config.github_oauth_client_id)
