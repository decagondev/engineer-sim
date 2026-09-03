from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Runtime configuration. Provider selection is a config swap (DIP payoff):
    run `fake` for free tests, `ollama` for free local dev, `anthropic` for
    quality passes and real sessions.
    """

    llm_provider: str = "fake"            # fake | ollama | anthropic
    ollama_model: str = "llama3.1"
    anthropic_model: str = "claude-sonnet-4-5"  # override via ANTHROPIC_MODEL
    groq_model: str = "llama-3.3-70b-versatile"  # override via GROQ_MODEL
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

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.1"),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
        )
