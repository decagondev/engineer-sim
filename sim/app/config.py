from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Runtime configuration. Provider selection is a config swap (DIP payoff):
    run `fake` for free tests, `ollama` for free local dev, `anthropic` for
    quality passes and real sessions.
    """

    llm_provider: str = "fake"            # fake | ollama | anthropic | groq
    ollama_model: str = "llama3.1"
    anthropic_model: str = "claude-sonnet-4-5"  # override via ANTHROPIC_MODEL
    groq_model: str = "openai/gpt-oss-120b"  # override via GROQ_MODEL
    db_path: str = "sim.db"
    scenario_path: str = ""               # empty => built-in demo scenario
    grader_calibrated: bool = False       # flip only after calibration passes
    env_provider: str = "local_folder"    # sandbox adapter
    sandbox_root: str = ".sandboxes"      # where per-session workdirs live
    sandbox_image: str = "python:3.11-slim"  # docker image for the sandbox
    sandbox_memory: str = "2g"
    sandbox_cpus: str = "2"
    sandbox_pids: str = "512"
    instructor_password: str = "$T0mV13w"   # light gate for the replay view
    github_token: str = ""                  # optional; raises GitHub API rate limit
    auth_mode: str = "password"             # password | firebase | fake
    firebase_project_id: str = ""
    firebase_web_api_key: str = ""
    firebase_auth_domain: str = ""
    firebase_credentials_json: str = ""     # service account JSON (optional)
    bootstrap_admin_email: str = ""
    persistence: str = "sqlite"             # sqlite | firestore
    byok_secret: str = ""                   # Fernet secret for per-user Groq keys
    public_base_url: str = ""               # e.g. https://worksim.example.com; else derived from requests
    work_mode: str = "auto"                 # auto | local | hosted (see sim/core/workflow.py)
    github_oauth_client_id: str = ""        # GitHub OAuth app (device flow) so Files can commit to a fork

    @property
    def hosted(self) -> bool:
        """Hosted deployments only offer the GitHub path for product scenarios.
        `auto` infers it from the presence of Firebase / Firestore."""
        mode = (self.work_mode or "auto").lower()
        if mode == "hosted":
            return True
        if mode == "local":
            return False
        return self.auth_mode == "firebase" or self.persistence in ("firestore", "firebase")

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.1"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            groq_model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
            db_path=os.environ.get("SIM_DB_PATH", "sim.db"),
            scenario_path=os.environ.get("SIM_SCENARIO", ""),
            grader_calibrated=os.environ.get("GRADER_CALIBRATED", "").lower()
            in ("1", "true", "yes"),
            env_provider=os.environ.get("ENV_PROVIDER", "local_folder"),
            sandbox_root=os.environ.get("SANDBOX_ROOT", ".sandboxes"),
            sandbox_image=os.environ.get("SANDBOX_IMAGE", "python:3.11-slim"),
            sandbox_memory=os.environ.get("SANDBOX_MEMORY", "2g"),
            sandbox_cpus=os.environ.get("SANDBOX_CPUS", "2"),
            sandbox_pids=os.environ.get("SANDBOX_PIDS", "512"),
            instructor_password=os.environ.get("INSTRUCTOR_PASSWORD", "$T0mV13w"),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            auth_mode=os.environ.get("AUTH_MODE", "password").lower(),
            firebase_project_id=os.environ.get("FIREBASE_PROJECT_ID", ""),
            firebase_web_api_key=os.environ.get("FIREBASE_WEB_API_KEY", ""),
            firebase_auth_domain=os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
            firebase_credentials_json=os.environ.get("FIREBASE_CREDENTIALS_JSON", ""),
            bootstrap_admin_email=os.environ.get("AUTH_BOOTSTRAP_ADMIN_EMAIL", ""),
            persistence=os.environ.get("PERSISTENCE", "sqlite").lower(),
            byok_secret=os.environ.get("BYOK_SECRET", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "").rstrip("/"),
            work_mode=os.environ.get("WORK_MODE", "auto").lower(),
            github_oauth_client_id=os.environ.get("GITHUB_OAUTH_CLIENT_ID", ""),
        )
