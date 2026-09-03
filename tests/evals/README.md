# Eval harness (real-model, non-gating)

These do NOT run in the normal `make test`. They hit a real model, assert with
tolerances over several runs, and cost money. They answer "does the persona
actually withhold the hidden need?" — which the deterministic suites cannot.

Run them explicitly against a real provider:

    LLM_PROVIDER=ollama pytest -m eval tests/evals
    LLM_PROVIDER=anthropic ANTHROPIC_MODEL=<current> pytest -m eval tests/evals

They skip automatically when LLM_PROVIDER=fake.
