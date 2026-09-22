"""SessionManager — resolves each session to a scenario and hands out a per-scenario
bundle of services. Shared stores (sqlite or Firestore, keyed by session_id) are
built once; scenario-specific services (cast/world/rubric/triggers/starter/seeds)
are built per scenario and cached.
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.app.config import Config
from sim.core.mail.mail_service import MailService
from sim.core.persona.responder import PersonaResponder
from sim.core.persona.unlock import UnlockEvaluator
from sim.core.scenario.scenario import Scenario
from sim.core.session.session_service import SessionService
from sim.core.tickets.ticket_service import TicketService


@dataclass
class Bundle:
    scenario: Scenario
    session_service: SessionService
    mail_service: MailService
    ticket_service: TicketService
    environment: object


class SessionManager:
    def __init__(self, config: Config, registry: dict[str, Scenario],
                 default_scenario_key: str, llm, judge_llm,
                 repo_files=None) -> None:
        from sim.adapters.persistence.stores import build_stores

        self._config = config
        self._registry = registry
        # Reads files out of a submitted public repo (duck-typed: read_file(url, path)).
        # Lets a repo submission feed the design doc to the assessor and grader.
        self.repo_files = repo_files
        self._default = (default_scenario_key if default_scenario_key in registry
                         else next(iter(registry)))
        stores = build_stores(config)
        self.repo = stores.repo
        self.unlock = stores.unlock
        self.mailstore = stores.mailstore
        self.ticketstore = stores.ticketstore
        self.settings = stores.settings
        self.submissions = stores.submissions
        self.users = stores.users
        self.session_registry = stores.session_registry
        self.cohorts = stores.cohorts
        self.session_files = stores.session_files
        self.grades = stores.grades
        self.reviews = stores.reviews
        from sim.adapters.llm.scoped_client import wrap_user_scoped_llm
        self.llm = wrap_user_scoped_llm(llm, users=self.users, config=config)
        self._responder = PersonaResponder(self.llm)
        self._judge = wrap_user_scoped_llm(judge_llm, users=self.users, config=config)
        self._cache: dict[str, Bundle] = {}

    # -- registry -----------------------------------------------------------
    @property
    def registry(self) -> dict[str, Scenario]:
        return self._registry

    def scenarios_meta(self) -> list[dict]:
        return [{"key": s.key, "title": s.title, "difficulty": s.difficulty,
                 "track": s.track, "role_label": s.role_label}
                for s in self._registry.values()]

    def default_scenario_key(self) -> str:
        return self._default

    # -- resolution ---------------------------------------------------------
    def resolve_scenario_key(self, session_id: str) -> str:
        key = self.settings.get_session_scenario(session_id)
        return key if key in self._registry else self._default

    def for_session(self, session_id: str) -> Bundle:
        return self.bundle_for(self.resolve_scenario_key(session_id))

    def bundle_for(self, scenario_key: str) -> Bundle:
        if scenario_key in self._cache:
            return self._cache[scenario_key]
        from sim.app.composition_root import build_director, build_environment
        sc = self._registry[scenario_key]
        mail = MailService(
            writer=self.repo, reader=self.repo, mail_store=self.mailstore,
            responder=self._responder, unlock_store=self.unlock,
            world=sc.world, cast=sc.cast, settings=self.settings)
        from sim.core.tickets.ticket_service import project_prefix
        tickets = TicketService(
            store=self.ticketstore, writer=self.repo, cast=sc.cast,
            seed_tickets=sc.tickets, project_key=project_prefix(sc.key))
        environment = build_environment(self._config, sc)
        session = SessionService(
            writer=self.repo, reader=self.repo, responder=self._responder,
            unlock_store=self.unlock, unlock_evaluator=UnlockEvaluator(self._judge),
            world=sc.world, cast=sc.cast, director=build_director(sc),
            mail_service=mail, ticket_service=tickets, settings=self.settings,
            primary_key=sc.primary_persona.key,
            track=sc.track, role_label=sc.role_label,
            design_lookup=lambda sid, env=environment, track=sc.track:
                self.lookup_design(sid, env, track))
        bundle = Bundle(sc, session, mail, tickets, environment)
        self._cache[scenario_key] = bundle
        return bundle


    # -- durable design lookup ----------------------------------------------
    def lookup_design(self, session_id: str, environment, track: str) -> str:
        """Where the learner's design doc lives when it is not in memory
        (fresh process, hosted restart). Order: the latest submission (the
        durable record), a repo submission's DESIGN.md, then the sandbox file.
        """
        sub = self.submissions.latest(session_id) if self.submissions else None
        if sub is not None:
            if sub.kind == "doc" or (sub.kind == "patch" and track != "product"):
                if sub.content.strip():
                    return sub.content
            if sub.kind == "repo" and self.repo_files is not None:
                text = self.repo_files.read_file(sub.content, "DESIGN.md") or ""
                if text.strip():
                    return text
        return _read_workspace_design(environment, session_id)


def _read_workspace_design(environment, session_id: str) -> str:
    from pathlib import Path
    if environment is None:
        return ""
    h = environment.handle(session_id)
    if h is None:
        return ""
    path = Path(h.workdir) / "DESIGN.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
