"""Undo pins (plan C1): every destructive flow can be taken back."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_restore_conversation_beats_the_tombstone(tmp_path, monkeypatch):
    """Delete tombstones the id for 60s; Undo is the one caller that
    wants it back and must not be refused."""
    from services import conversation_service as conversations

    monkeypatch.setattr(conversations, "conversations_dir", lambda: tmp_path)
    cid = "undo-test"
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert conversations.save_conversation(cid, messages, title="undo me")

    assert conversations.delete_conversation(cid)
    assert conversations.load_conversation(cid) is None

    assert conversations.restore_conversation(cid, messages, title="undo me")
    restored = conversations.load_conversation(cid)
    assert restored is not None
    assert restored["messages"] == messages
    assert restored["title"] == "undo me"


def test_exchange_bounds_cover_whole_exchanges():
    from screens.chat_screen import _exchange_bounds

    turns = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ]
    assert _exchange_bounds(turns, 0) == (0, 2)  # user takes its answer
    assert _exchange_bounds(turns, 1) == (0, 2)  # answer takes its question
    assert _exchange_bounds(turns, 2) == (2, 4)
    # A view-only row (error bubble) stands alone.
    error = [{"role": "error", "content": ""}]
    assert _exchange_bounds(error, 0) == (0, 1)


def test_delete_flows_carry_the_undo_words():
    root = Path(__file__).resolve().parents[1]
    chat = (root / "src" / "screens" / "chat_screen.py").read_text(encoding="utf-8")
    history = (root / "src" / "screens" / "history_screen.py").read_text(
        encoding="utf-8"
    )
    for source in (chat, history):
        assert "This cannot be undone." not in source, (
            "every destructive dialog now promises an Undo instead"
        )
    assert chat.count('action="Undo"') >= 4
    assert 'action="Undo"' in history
    assert "restore_conversation" in chat
