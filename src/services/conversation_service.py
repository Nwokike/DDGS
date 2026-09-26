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


def flat_from_turns(turns: list[dict]) -> list[dict]:
    """Project a rendered transcript into the flat pairs that are stored.

    The screen owns exactly one list - `turns`, the thing the user sees -
    and this is the only place it becomes `{"role", "content"}`. What is
    written to disk and what the model is handed are the same projection,
    so they cannot disagree.

    This exists because the second list used to live in memory beside the
    first: a delete updated one and persisted the other, and the message
    came straight back from disk. LM Router keeps one transcript too
    (`lm-router/src/services/history.py`), projecting kani's history into
    display messages rather than mirroring both directions.
    """
    flat: list[dict] = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        if role not in ("user", "assistant"):
            continue
        text = turn.get("text")
        if not isinstance(text, str) or not text.strip():
            # An error row with nothing behind it is not something the
            # model should be told the user said.
            continue
        flat.append({"role": role, "content": text})
    return flat


# Ids deleted recently. A save already in flight when the user deletes a
# chat would otherwise rewrite the file and resurrect it after the next
# restart, which looks exactly like "delete does nothing".
_tombstones: dict[str, float] = {}
_TOMBSTONE_TTL = 60.0


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
    """Write atomically; two saves racing must not fight over one file.

    The fixed ".json.tmp" name meant a turn-final save and a cancel save
    arriving together collided on Windows (Errno 13 / WinError 32 in the
    field: one temp file, opened and renamed by two writers). Each write
    gets its own temp name now, and the replace retries briefly if a
    reader still holds the target open.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("conversation write failed (%s): %s", path.name, exc)
        return False
    text = json.dumps(payload, ensure_ascii=False)
    for attempt in range(3):
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            return True
        except (OSError, ValueError, TypeError) as exc:
            try:
                tmp.unlink()
            except OSError:
                pass
            if attempt == 2:
                logger.warning("conversation write failed (%s): %s", path.name, exc)
                return False
            time.sleep(0.05 * (attempt + 1))
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

    Returns True on success. Pure IO: the caller re-lists if the menu
    needs refreshing.
    """
    if not conversation_id:
        return False
    now = time.time()
    # A save that was queued before the delete must not recreate the file.
    _prune_tombstones(now)
    if conversation_id in _tombstones:
        logger.debug("refusing to save %s: it was just deleted", conversation_id)
        return False
    if not messages:
        return delete_conversation(conversation_id)
    existing = _read(_path(conversation_id)) or {}
    payload = {
        "schema": SCHEMA,
        "id": conversation_id,
        "title": title or existing.get("title") or _title_from_messages(messages),
        "created": existing.get("created") or now,
        "updated": now,
        # Enforced here rather than only in the UI: migration and any
        # future caller go through this function too, and a constant the
        # service does not enforce is a lie about retention.
        "messages": list(messages)[-CONVERSATION_MESSAGE_CAP:],
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


def _prune_tombstones(now: float) -> None:
    for key, stamp in list(_tombstones.items()):
        if now - stamp > _TOMBSTONE_TTL:
            _tombstones.pop(key, None)


def delete_conversation(conversation_id: str) -> bool:
    """Delete one conversation. False means the file is still there."""
    _tombstones[str(conversation_id)] = time.time()
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


async def clear_legacy_history(storage) -> None:
    """Drop the old flat history once it has been migrated.

    Without this, "delete all chats" emptied the directory, the next launch
    found it empty, and the stale legacy value was migrated straight back as
    a new "Previous chat". A chat the user had deliberately deleted came
    back on every restart.
    """
    try:
        await storage.set_assistant_history("[]")
        await storage.flush()
        logger.info("cleared the legacy assistant history after migration")
    except Exception as exc:
        logger.warning("could not clear the legacy assistant history: %s", exc)


def refresh_state() -> list[dict]:
    """Re-read the summary rows.

    Kept as a single call site so callers do not each re-list the
    directory. The rows are returned rather than parked on observable
    state: nothing read the old mirror, and an observable write in the
    save path was one more way a dead session could stop persistence.
    """
    return list_conversations()


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
