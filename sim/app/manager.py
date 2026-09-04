"""SessionManager — resolves each session to a scenario and hands out a per-scenario
bundle of services. Shared stores (one SQLite file, keyed by session_id) are built
once; scenario-specific services (cast/world/rubric/triggers/starter/seeds) are built
per scenario and cached.
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
                 default_scenario_key: str, llm, judge_llm) -> None:
        from sim.adapters.persistence.sqlite_repo import SqliteMessageRepository
        from sim.adapters.persistence.sqlite_state import SqliteUnlockStore
        from sim.adapters.persistence.sqlite_mail import SqliteMailStore
        from sim.adapters.persistence.sqlite_tickets import SqliteTicketStore
        from sim.adapters.persistence.sqlite_settings import SqliteSettingsStore
        from sim.adapters.persistence.sqlite_submissions import SqliteSubmissionStore

        self._config = config
        self._registry = registry
        self._default = (default_scenario_key if default_scenario_key in registry
                         else next(iter(registry)))
        # shared, per-DB stores (all keyed by session_id)
        self.repo = SqliteMessageRepository(config.db_path)
        self.unlock = SqliteUnlockStore(config.db_path)
        self.mailstore = SqliteMailStore(config.db_path)
        self.ticketstore = SqliteTicketStore(config.db_path)
        self.settings = SqliteSettingsStore(config.db_path)
        self.submissions = SqliteSubmissionStore(config.db_path)
        self._responder = PersonaResponder(llm)
        self._judge = judge_llm
        self._cache: dict[str, Bundle] = {}

    # -- registry -----------------------------------------------------------
    @property
    def registry(self) -> dict[str, Scenario]:
        return self._registry

    def scenarios_meta(self) -> list[dict]:
        return [{"key": s.key, "title": s.title, "difficulty": s.difficulty}
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
        session = SessionService(
            writer=self.repo, reader=self.repo, responder=self._responder,
            unlock_store=self.unlock, unlock_evaluator=UnlockEvaluator(self._judge),
            world=sc.world, cast=sc.cast, director=build_director(sc),
            mail_service=mail, ticket_service=tickets, settings=self.settings,
            primary_key=sc.primary_persona.key)
        bundle = Bundle(sc, session, mail, tickets,
                        build_environment(self._config, sc))
        self._cache[scenario_key] = bundle
        return bundle
