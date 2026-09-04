from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """Something the director makes happen — e.g. an uninvited stakeholder
    posts a message.
    """

    event_id: str
    persona_key: str
    channel: str
    content: str
    kind: str = "chat"        # "chat" | "email" | "ticket"
    subject: str = ""
    issue_type: str = ""      # story | task | bug | spike (tickets)
    priority: str = ""
    labels: str = ""
