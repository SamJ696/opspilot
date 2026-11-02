from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

INCIDENT_ID = re.compile(r"\bINC-\d+\b", re.IGNORECASE)
APPROVE = re.compile(r"^approve\s+(INC-\d+)\s*$", re.IGNORECASE)
REJECT = re.compile(r"^reject\s+(INC-\d+)\s*$", re.IGNORECASE)
STATUS = re.compile(r"^status\s+(INC-\d+)\s*$", re.IGNORECASE)
MENTION_PREFIXES = ("@opspilot", "!opspilot")


class CommandKind(str, Enum):
    INCIDENT = "incident"
    APPROVE = "approve"
    REJECT = "reject"
    STATUS = "status"
    HELP = "help"
    IGNORE = "ignore"


@dataclass(frozen=True)
class ParsedCommand:
    kind: CommandKind
    incident_id: str = ""
    incident_text: str = ""
    raw: str = ""


def _normalize_incident_id(value: str) -> str:
    match = INCIDENT_ID.search(value)
    if not match:
        return value.upper()
    return match.group(0).upper()


def strip_invocation(body: str) -> str:
    text = body.strip()
    lowered = text.lower()
    for prefix in MENTION_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip(" \t:,—-")
    return text


def parse_command(body: str) -> ParsedCommand:
    raw = body.strip()
    if not raw:
        return ParsedCommand(kind=CommandKind.IGNORE, raw=raw)

    lowered = raw.lower()
    if lowered in {"help", "help opspilot", "@opspilot help", "!opspilot help"}:
        return ParsedCommand(kind=CommandKind.HELP, raw=raw)

    match = APPROVE.match(raw)
    if match:
        return ParsedCommand(
            kind=CommandKind.APPROVE,
            incident_id=_normalize_incident_id(match.group(1)),
            raw=raw,
        )

    match = REJECT.match(raw)
    if match:
        return ParsedCommand(
            kind=CommandKind.REJECT,
            incident_id=_normalize_incident_id(match.group(1)),
            raw=raw,
        )

    match = STATUS.match(raw)
    if match:
        return ParsedCommand(
            kind=CommandKind.STATUS,
            incident_id=_normalize_incident_id(match.group(1)),
            raw=raw,
        )

    if "approve" in lowered or "reject" in lowered:
        if not APPROVE.match(raw) and not REJECT.match(raw):
            return ParsedCommand(kind=CommandKind.IGNORE, raw=raw)

    incident_text = strip_invocation(raw)
    if not incident_text:
        return ParsedCommand(kind=CommandKind.HELP, raw=raw)

    if incident_text.lower() in {"help", "status"}:
        return ParsedCommand(kind=CommandKind.HELP, raw=raw)

    return ParsedCommand(
        kind=CommandKind.INCIDENT,
        incident_text=incident_text,
        raw=raw,
    )


HELP_TEXT = """OpsPilot commands:
- `@opspilot <incident description>` — start an investigation
- `approve INC-1001` — approve remediation for that incident
- `reject INC-1001` — reject remediation
- `status INC-1001` — show incident status
- `help` — show this message

Recovery actions are simulated and require an explicit approve command with the incident ID."""
