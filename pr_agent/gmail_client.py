"""Gmail access. Scopes allow creating drafts and reading threads. There is no send permission."""
import base64
from datetime import datetime
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import ROOT

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def service():
    token = ROOT / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secrets = ROOT / "credentials.json"
            if not secrets.exists():
                raise SystemExit("credentials.json not found. See README, 'Connect Gmail'.")
            creds = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def my_address(svc):
    return svc.users().getProfile(userId="me").execute()["emailAddress"]


def create_draft(svc, to, subject, body, sender=None, thread_id=None, in_reply_to=None):
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if sender:
        msg["From"] = sender
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    payload = {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    d = svc.users().drafts().create(userId="me", body=payload).execute()
    return d["id"], d["message"]["threadId"]


def draft_exists(svc, draft_id):
    if not draft_id:
        return False
    try:
        svc.users().drafts().get(userId="me", id=draft_id, format="minimal").execute()
        return True
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise


def thread_state(svc, thread_id, me):
    """Work out whether the thread has been sent and whether anyone else has replied."""
    try:
        t = svc.users().threads().get(
            userId="me", id=thread_id, format="metadata", metadataHeaders=["From", "Message-ID"]
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return None
        raise
    sent_ms, replied, last_id = [], False, None
    for m in t.get("messages", []):
        labels = m.get("labelIds", [])
        if "DRAFT" in labels:
            continue
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        if "SENT" in labels or me.lower() in headers.get("from", "").lower():
            sent_ms.append(int(m["internalDate"]))
            last_id = headers.get("message-id", last_id)
        else:
            replied = True
            last_id = headers.get("message-id", last_id)
    last_sent = datetime.fromtimestamp(max(sent_ms) / 1000).isoformat(timespec="seconds") if sent_ms else ""
    return {"sent": bool(sent_ms), "last_sent": last_sent, "replied": replied, "last_message_id": last_id}
