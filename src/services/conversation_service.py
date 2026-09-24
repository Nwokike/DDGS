"""Assistant conversation history: one file per chat under data/conversations/.

Follows the layout LM Router proved (`lm-router/src/services/history.py`):
a directory of `<id>.json` files, newest first, titled from the first user
message. Two deliberate differences:

  - no Python 2 `except OSError, ValueError:` anywhere; that file raises
    SyntaxError on import, and a history feature that cannot be imported is
    not a history feature
  - failures are reported, never swallowed. A delete that did not delete
    must not look like it did.

These are durable user data, so this lives in the DATA directory, not the
cache. The 50-chat cap prunes oldest-first and the caller is told how many
went away, because silently deleting someone's conversation is not
acceptable.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from core.state import state
from core.storage_paths import data_dir

logger = logging.getLogger(__name__)

CONVERSATIONS_DIRNAME = "conversations"
# 50 as chosen: plenty for daily use, small on disk, and the menu stays
# scannable. Pruning is announced to the user, never silent.
MAX_CONVERSATIONS = 50
# Per-chat retention. 400 messages is far beyond a real conversation and
# stops one endless thread from growing the file without bound.
CONVERSATION_MESSAGE_CAP = 400
TITLE_LENGTH = 48
SCHEMA = 1


def conversations_dir() -> Path:
    path = data_dir() / CONVERSATIONS_DIRNAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("conversations dir unavailable: %s", exc)
    return path


def _title_from_messages(messages: list[dict]) -> str:
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                text = " ".join(content.split())
                return text[:TITLE_LENGTH]
    return "New chat"


def _path(conversation_id: str) -> Path:
    safe = "".join(ch for ch in str(conversation_id) if ch.isalnum() or ch in "_-")
    return conversations_dir() / f"{safe}.json"


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    if not isinstance(data.get("messages"), list):
        data["messages"] = []
    return data


def _write(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return True
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("conversation write failed (%s): %s", path.name, exc)
        return False


def new_conversation_id() -> str:
    return uuid.uuid4().hex[:12]


def list_conversations() -> list[dict]:
    """Summary rows, newest first. Never raises."""
    items: list[dict] = []
    try:
        paths = list(conversations_dir().glob("*.json"))
    except OSError as exc:
        logger.warning("conversation list failed: %s", exc)
        return items
    for path in paths:
        data = _read(path)
        if data is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = data.get("updated") or 0.0
        items.append(
            {
                "id": str(data.get("id") or path.stem),
                "title": str(
                    data.get("title")
                    or _title_from_messages(data.get("messages") or [])
                ),
                "updated": float(data.get("updated") or mtime),
                "message_count": len(data.get("messages") or []),
            }
        )
    items.sort(key=lambda item: item["updated"], reverse=True)
    return items


def load_conversation(conversation_id: str) -> dict | None:
    return _read(_path(conversation_id))


def save_conversation(
    conversation_id: str, messages: list[dict], *, title: str | None = None
) -> bool:
    """Persist a conversation and prune past the cap.

    An empty conversation is removed rather than saved: a brand-new chat
    that the user has not typed into yet has no history value, and keeping
    those would fill the menu with blank rows.

    Returns True on success. `state.conversations` is refreshed by the
    caller on the UI loop; this function is pure IO.
    """
    if not conversation_id:
        return False
    if not messages:
        return delete_conversation(conversation_id)
    now = time.time()
    existing = _read(_path(conversation_id)) or {}
    payload = {
        "schema": SCHEMA,
        "id": conversation_id,
        "title": title or existing.get("title") or _title_from_messages(messages),
        "created": existing.get("created") or now,
        "updated": now,
        "messages": messages or [],
    }
    if not _write(_path(conversation_id), payload):
        return False
    prune_conversations(protect=conversation_id)
    return True


def prune_conversations(
    limit: int = MAX_CONVERSATIONS, *, protect: str = ""
) -> int:
    """Delete the oldest conversations past `limit`. Returns how many went.

    The active conversation, and `protect` (normally the one just saved),
    are never pruned: losing the chat you are in the middle of, or the one
    that was written a moment ago, is the worst possible outcome here.
    """
    items = list_conversations()
    if len(items) <= limit:
        return 0
    keep = {state.active_conversation, protect}
    # list_conversations is newest-first, so the oldest are at the END.
    victims = [item for item in reversed(items) if item["id"] not in keep]
    overflow = len(items) - limit
    removed = 0
    for item in victims:
        if removed >= overflow:
            break
        if delete_conversation(item["id"]):
            removed += 1
    if removed:
        logger.info("pruned %d conversations past the %d limit", removed, limit)
    return removed


def delete_conversation(conversation_id: str) -> bool:
    """Delete one conversation. False means the file is still there."""
    try:
        _path(conversation_id).unlink()
        return True
    except FileNotFoundError:
        return True  # already gone: the user's intent is satisfied
    except OSError as exc:
        logger.warning("conversation delete failed (%s): %s", conversation_id, exc)
        return False


def delete_all() -> tuple[int, int]:
    """Delete every conversation. Returns (deleted, failed)."""
    deleted = failed = 0
    for item in list_conversations():
        if delete_conversation(item["id"]):
            deleted += 1
        else:
            failed += 1
    return deleted, failed


def migrate_legacy_history(legacy: list[dict]) -> str | None:
    """Wrap the old flat assistant_history into one conversation.

    Before per-chat history existed, DDGS kept a single capped message list
    in storage. Converting it once means an upgrade never shows the user an
    empty history for a chat they already had. Returns the new id, or None
    when there was nothing to migrate.
    """
    messages = [m for m in (legacy or []) if isinstance(m, dict)]
    if not messages:
        return None
    conversation_id = new_conversation_id()
    if save_conversation(conversation_id, messages, title="Previous chat"):
        logger.info("migrated legacy assistant history into %s", conversation_id)
        return conversation_id
    return None


def refresh_state() -> list[dict]:
    """Reload the summary rows into observable state (UI loop only)."""
    state.conversations = list_conversations()
    return state.conversations


def ensure_active() -> str:
    """Return the active conversation id, creating one if needed."""
    active = state.active_conversation
    if active and load_conversation(active) is not None:
        return active
    active = new_conversation_id()
    state.active_conversation = active
    return active


def relative_time(timestamp: float) -> str:
    """'just now' / '12m ago' / '3h ago' / 'Sep 20' for the history menu."""
    try:
        delta = max(0.0, time.time() - float(timestamp))
    except (TypeError, ValueError):
        return ""
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 7 * 86400:
        return f"{int(delta // 86400)}d ago"
    return time.strftime("%b %d", time.localtime(float(timestamp)))


def summarize(item: dict[str, Any]) -> str:
    """One-line subtitle for a history row."""
    count = int(item.get("message_count") or 0)
    messages = f"{count} message" + ("" if count == 1 else "s")
    when = relative_time(item.get("updated") or 0)
    return f"{messages} · {when}" if when else messages
