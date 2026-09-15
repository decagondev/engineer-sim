"""Read or update the Firebase Auth email templates for this project.

    python tools/email_templates.py show
    python tools/email_templates.py apply            # set the simulator wording
    python tools/email_templates.py apply --app-name "Your name here"

Needs FIREBASE_PROJECT_ID and a service account (FIREBASE_CREDENTIALS_JSON as a
path or inline JSON, or GOOGLE_APPLICATION_CREDENTIALS). Templates support the
placeholders %LINK%, %EMAIL%, %APP_NAME% and %DISPLAY_NAME%.

Firebase lets any project change the sender name and subject. Customising the
message *body* is only honoured once a custom sending domain is verified under
Authentication > Templates; until then Firebase keeps its stock body and this
tool tells you so.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim.adapters.auth.service_account import service_account_credentials  # noqa: E402

API = "https://identitytoolkit.googleapis.com/admin/v2/projects/{project}/config"

RESET_SUBJECT = "Set your password for %APP_NAME%"
RESET_BODY = """<p>Hello,</p>
<p>Your instructor has created an account for you on <b>%APP_NAME%</b>
using this email address (%EMAIL%).</p>
<p>Choose a password to get started:</p>
<p><a href="%LINK%">Set my password</a></p>
<p>The link works once and expires after a short while. If it has expired,
open the sign-in page and use <i>Forgot password?</i> to get a new one.</p>
<p>If you were not expecting this, you can ignore this email.</p>
"""


def _session(project: str):
    import httpx
    from google.auth.transport.requests import Request
    creds = service_account_credentials(os.environ.get("FIREBASE_CREDENTIALS_JSON", ""))
    if creds is None:
        sys.exit("No service account: set FIREBASE_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")
    creds.refresh(Request())
    return httpx.Client(timeout=20, headers={"Authorization": f"Bearer {creds.token}"}), API.format(project=project)


def show(project: str) -> dict:
    http, url = _session(project)
    r = http.get(url)
    r.raise_for_status()
    cfg = r.json()
    send = (cfg.get("notification") or {}).get("sendEmail") or {}
    print(json.dumps({
        "resetPasswordTemplate": send.get("resetPasswordTemplate"),
        "verifyEmailTemplate": send.get("verifyEmailTemplate"),
        "dnsInfo": send.get("dnsInfo"),
        "method": send.get("method"),
    }, indent=2))
    return cfg


def apply(project: str, app_name: str, sender_name: str) -> None:
    http, url = _session(project)
    body = RESET_BODY
    payload = {"notification": {"sendEmail": {"resetPasswordTemplate": {
        "senderDisplayName": sender_name,
        "subject": RESET_SUBJECT.replace("%APP_NAME%", app_name),
        "body": body.replace("%APP_NAME%", app_name),
        "bodyFormat": "HTML",
    }}}}
    def patch(fields):
        mask = ",".join(f"notification.sendEmail.resetPasswordTemplate.{k}" for k in fields)
        return http.patch(url, params={"updateMask": mask}, json=payload)
    # Firebase only accepts the subject and body once a custom sending domain
    # is verified; the sender name is always writable. Try the most, keep the
    # most it will take.
    attempts = [
        ("sender name, subject and body", ("senderDisplayName", "subject", "body", "bodyFormat")),
        ("sender name and subject", ("senderDisplayName", "subject")),
        ("sender name only", ("senderDisplayName",)),
    ]
    applied, r = None, None
    for label, fields in attempts:
        r = patch(fields)
        if r.status_code == 200:
            applied = label
            break
        if "EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED" not in r.text:
            break
    if r is None or r.status_code != 200:
        sys.exit(f"update failed ({r.status_code}): {r.text}")
    tpl = ((r.json().get("notification") or {}).get("sendEmail") or {}).get("resetPasswordTemplate") or {}
    print(f"Applied: {applied}")
    print(json.dumps(tpl, indent=2))
    if applied != attempts[0][0]:
        print("\nFirebase refused the rest (EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED). Subject and "
              "body become editable once a sending domain is verified under "
              "Authentication > Templates > Customize domain; re-run this tool afterwards. "
              "The console may also let you edit the subject by hand before that.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["show", "apply"])
    ap.add_argument("--project", default=os.environ.get("FIREBASE_PROJECT_ID", ""))
    ap.add_argument("--app-name", default="the Engineering Flight Simulator")
    ap.add_argument("--sender-name", default="Engineering Flight Simulator")
    a = ap.parse_args()
    if not a.project:
        sys.exit("--project or FIREBASE_PROJECT_ID required")
    if a.action == "show":
        show(a.project)
    else:
        apply(a.project, a.app_name, a.sender_name)


if __name__ == "__main__":
    main()
