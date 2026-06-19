"""Scrub secrets from BSON dump before pushing to GitHub.

What this does:
- config.bson: zero out bud_inbound_token and nine_outbound_token
- agent_letters.bson: regex-redact any embedded tokens / API keys in letter bodies
- All other collections: scanned for high-entropy strings, redacted if matched

Run from /app/memory/migration/mongo_dump/bud_database/.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
import bson

DUMP_DIR = Path("/app/memory/migration/mongo_dump/bud_database")

# Patterns that indicate a live secret
SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED-OPENAI]"),
    (re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\b"), "[REDACTED-SENDGRID]"),
    (re.compile(r"\bAC[a-f0-9]{32}\b"), "[REDACTED-TWILIO-SID]"),
    (re.compile(r"\bSK[a-f0-9]{32}\b"), "[REDACTED-TWILIO-KEY]"),
    (re.compile(r"\bEAA[A-Za-z0-9]{40,}\b"), "[REDACTED-FB-TOKEN]"),
    # Azure AD app secrets: short prefix + ~ + 30+ chars (Microsoft client secret format)
    (re.compile(r"\b[A-Za-z0-9]{1,4}~[A-Za-z0-9_~\-]{30,}\b"), "[REDACTED-AZURE-SECRET]"),
    # Generic high-entropy 40+ char URL-safe base64 tokens
    (re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "[REDACTED-TOKEN]"),
]


def redact_str(s: str) -> str:
    if not isinstance(s, str):
        return s
    out = s
    for rx, rep in SECRET_PATTERNS:
        out = rx.sub(rep, out)
    return out


def walk(obj):
    if isinstance(obj, dict):
        return {k: walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(x) for x in obj]
    if isinstance(obj, str):
        return redact_str(obj)
    return obj


def scrub_bson(path: Path) -> int:
    """Returns count of docs rewritten."""
    if not path.exists() or path.stat().st_size == 0:
        return 0
    raw = path.read_bytes()
    docs = bson.decode_all(raw)
    cleaned = [walk(d) for d in docs]
    out = b"".join(bson.encode(d) for d in cleaned)
    path.write_bytes(out)
    return len(cleaned)


def main():
    if not DUMP_DIR.exists():
        print(f"ERR: {DUMP_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    # Special-case config: blank the known token fields entirely
    config_path = DUMP_DIR / "config.bson"
    if config_path.exists():
        raw = config_path.read_bytes()
        docs = bson.decode_all(raw)
        for d in docs:
            if d.get("id") == "bud":
                d["bud_inbound_token"] = "[REDACTED-WILL-REGENERATE]"
                d["nine_outbound_token"] = None
        config_path.write_bytes(b"".join(bson.encode(d) for d in docs))
        print(f"config.bson: rewrote {len(docs)} docs (tokens nulled)")

    # Sweep all remaining bson files with regex redaction
    for path in sorted(DUMP_DIR.glob("*.bson")):
        if path.name == "config.bson":
            continue
        try:
            n = scrub_bson(path)
            if n:
                print(f"{path.name}: scanned {n} docs")
        except Exception as e:
            print(f"{path.name}: FAIL {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
