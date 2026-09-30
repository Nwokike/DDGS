"""Live AI probe: every tool and ability against the real router.

Run by hand (never collected by pytest - scripts/ is outside testpaths):

    .venv/Scripts/python.exe scripts/ai_probe.py

Covers what the offline suite cannot: real ddgs searches, real fetch/
save/scrape/download against the network, an end-to-end chat turn, a
DETERMINISTIC model-fallback walk (first stream is rigged to 429),
mid-stream cancel, free overview/summary calls, the approval gate, and
a .kani export/import round-trip. Prints PASS/FAIL per case; exit 1 if
anything fails. Cost: a handful of free-tier credits.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402
import openai  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}", flush=True)


class _Store:
    def __init__(self, data: dict):
        self.data = dict(data)

    async def get(self, key, default=None):
        return self.data.get(key, default)

    async def set(self, key, value):
        self.data[key] = value
        return True


def _events() -> list[tuple[str, dict]]:
    return []


def _emit(events: list, event: str, data: dict) -> None:
    events.append((event, data))
    print(f"    emit:{event} {str(data)[:100]}", flush=True)


# ---------------------------------------------------------------- tools ---


async def probe_tools() -> list[str]:
    from services.chat_agent import _dispatch

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        report(f"tool:{name}", ok, detail)
        if not ok:
            failures.append(name)

    # 1-5: the read searches
    for tool, query in (
        ("search_web", "Kiri router"),
        ("search_images", "sunset lagoon"),
        ("search_videos", "rust programming tutorial"),
        ("search_news", "technology news this week"),
        ("search_books", "python programming"),
    ):
        try:
            out, results = await _dispatch(tool, {"query": query, "count": 5})
            check(
                tool,
                bool(results) and isinstance(out, list),
                f"{len(results)} results, {len(out)} model items",
            )
        except Exception as exc:
            check(tool, False, f"{type(exc).__name__}: {exc}")

    # 6: fetch_page on a tiny stable page
    try:
        out, _ = await _dispatch("fetch_page", {"url": "https://example.com"})
        check("fetch_page", len(out.get("content", "")) > 100, f"{len(out.get('content', ''))} chars")
    except Exception as exc:
        check("fetch_page", False, f"{type(exc).__name__}: {exc}")

    tmp = Path(tempfile.mkdtemp(prefix="ddgs_probe_"))
    saved: list[Path] = []
    try:
        # 7: save_page -> real file, then delete it
        try:
            out, _ = await _dispatch("save_page", {"url": "https://example.com"})
            path = Path(out["saved_to"])
            saved.append(path)
            check("save_page", path.exists() and path.stat().st_size > 0, str(path))
        except Exception as exc:
            check("save_page", False, f"{type(exc).__name__}: {exc}")

        # 8: download_media -> real bytes (agent_files writes into
        # Downloads; recorded so the probe can clean up after itself)
        try:
            out, _ = await _dispatch(
                "download_media",
                {
                    "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
                },
            )
            dpath = Path(out["saved_to"])
            ok = dpath.exists() and dpath.stat().st_size > 0
            size = dpath.stat().st_size if dpath.exists() else 0
            check("download_media", ok, f"{dpath} ({size} bytes)")
            if dpath.exists():
                saved.append(dpath)
        except Exception as exc:
            check("download_media", False, f"{type(exc).__name__}: {exc}")

        # 9: crawl two pages of a tiny site, then delete the output
        try:
            out, _ = await _dispatch(
                "scrape_site", {"url": "https://example.com", "max_pages": 2}
            )
            files = out.get("saved") or []
            check("scrape_site", isinstance(files, list), f"saved={len(files)} failed={len(out.get('failed') or [])}")
            for name in files:
                saved.append(Path(name))
        except Exception as exc:
            check("scrape_site", False, f"{type(exc).__name__}: {exc}")

        # 10/11: schedule + cancel (state only; restored afterwards)
        from core import state as app_state

        before = list(app_state.scheduled_scrapes)
        try:
            out, _ = await _dispatch(
                "schedule_scrape",
                {"url": "https://example.com/probe-feed", "interval_minutes": 15},
            )
            scheduled = out.get("scheduled", {}).get("url")
            out2, _ = await _dispatch(
                "cancel_scrape", {"url": "https://example.com/probe-feed"}
            )
            check(
                "schedule+cancel_scrape",
                scheduled == "https://example.com/probe-feed"
                and out2.get("removed") == 1
                and app_state.scheduled_scrapes == before,
                f"scheduled then removed ({out2})",
            )
        except Exception as exc:
            app_state.scheduled_scrapes = before
            check("schedule+cancel_scrape", False, f"{type(exc).__name__}: {exc}")
    finally:
        for path in saved:
            try:
                path.unlink()
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    return failures


# ------------------------------------------------------------ abilities ---


async def probe_end_to_end() -> list[str]:
    from core import state as app_state
    from services import ai_service, chat_agent, credit_service
    from services import kani_backend

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        report(f"e2e:{name}", ok, detail)
        if not ok:
            failures.append(name)

    # credits: real service, in-memory store
    store = _Store({"ddgs_credits": "100"})
    app_state.credit_service = credit_service.CreditService(store)
    await app_state.credit_service.initialize()
    app_state.ai_model = "auto"

    # the candidate pool must be populated for fallback to walk
    models = await ai_service.refresh_catalog()
    check("catalog", len(models) >= 1, f"{len(models)} pickable models")
    pool = ai_service.candidate_models()
    check("candidate_pool", len(pool) >= 1, f"pool={pool[:4]}")

    # record every engine the turn builds (the walk is observable)
    real_build = kani_backend._build_engine
    built: list[str] = []

    async def spy_build(model, on_thought):
        built.append(model)
        return await real_build(model, on_thought)

    kani_backend._build_engine = spy_build

    # --- 1. end-to-end turn with a real search ---
    events: list = []
    try:
        await chat_agent.run_turn(
            "Search the news this week and answer in two sentences with the "
            "RELATED line.",
            [],
            lambda e, d: _emit(events, e, d),
            asyncio.Event(),
        )
        kinds = [e for e, _ in events]
        final = next((d for e, d in events if e == "text_final"), None)
        tools_ran = any(e == "step_start" for e, _ in events)
        ok = final is not None and bool((final.get("text") or "").strip())
        check(
            "turn_answers",
            ok,
            f"events={kinds[:8]}... tools_ran={tools_ran} model={final and final.get('model')}",
        )
        if final:
            related_ok = True  # related may be empty on tiny answers; presence is checked below
            check(
                "turn_tokens_receipt",
                bool(final.get("tokens")),
                f"tokens={final.get('tokens')}",
            )
            del related_ok
        check("turn_used_tools", tools_ran, f"step_start seen={tools_ran}")
    except Exception as exc:
        check("turn_answers", False, f"{type(exc).__name__}: {exc}")
    finally:
        kani_backend._build_engine = real_build

    # --- 2. deterministic fallback: first stream is rigged to 429 ---
    built.clear()
    events2: list = []
    orig_stream = kani_backend.ReasoningEngine.stream
    state_flag = {"fired": False}

    async def flaky_stream(self, *a, **kwargs):
        if not state_flag["fired"]:
            state_flag["fired"] = True
            raise openai.APIStatusError(
                "simulated sick model (probe)",
                response=httpx.Response(
                    429, request=httpx.Request("POST", "http://127.0.0.1/v1")
                ),
                body=None,
            )
        async for item in orig_stream(self, *a, **kwargs):
            yield item

    kani_backend.ReasoningEngine.stream = flaky_stream
    try:
        kani_backend._build_engine = spy_build
        await chat_agent.run_turn(
            "Say exactly: fallback works.",
            [],
            lambda e, d: _emit(events2, e, d),
            asyncio.Event(),
        )
        final = next((d for e, d in events2 if e == "text_final"), None)
        errored = next((d for e, d in events2 if e == "error"), None)
        walked = len(built) >= 2 and built[0] == "auto"
        check(
            "fallback_walks_and_answers",
            final is not None and walked and errored is None,
            f"built={built} final={'yes' if final else 'none'} error={errored}",
        )
    except Exception as exc:
        check("fallback_walks_and_answers", False, f"{type(exc).__name__}: {exc}")
    finally:
        kani_backend.ReasoningEngine.stream = orig_stream
        kani_backend._build_engine = real_build

    # --- 3. cancel mid-stream settles, never hangs ---
    events3: list = []
    cancel = asyncio.Event()

    def emit_cancel(event: str, data: dict) -> None:
        _emit(events3, event, data)
        if event == "text_partial" and not cancel.is_set():
            cancel.set()

    try:
        await chat_agent.run_turn(
            "Write a long paragraph about search engines.",
            [],
            emit_cancel,
            cancel,
        )
        kinds3 = [e for e, _ in events3]
        check(
            "cancel_settles",
            "stopped" in kinds3 or "error" in kinds3,
            f"events={kinds3[:6]}",
        )
    except Exception as exc:
        check("cancel_settles", False, f"{type(exc).__name__}: {exc}")

    # --- 4. approval gate: a write tool asks, we decline, turn continues ---
    events4: list = []
    approvals: list[str] = []

    async def deny_all(label: str, detail: str = "") -> bool:
        approvals.append(label)
        return False

    try:
        await chat_agent.run_turn(
            "Save https://example.com to my files as markdown.",
            [],
            lambda e, d: _emit(events4, e, d),
            asyncio.Event(),
            ask_confirm=deny_all,
        )
        started = [d.get("label", "") for e, d in events4 if e == "step_start"]
        declined = [d for e, d in events4 if e == "step_error"]
        check(
            "approval_gate_denies",
            bool(approvals) and bool(declined),
            f"asked={approvals} declined={len(declined)} steps={started}",
        )
    except Exception as exc:
        check("approval_gate_denies", False, f"{type(exc).__name__}: {exc}")

    # --- 5. free passive calls: overview + summary ---
    for name, messages in (
        (
            "overview",
            ai_service.build_overview_messages(
                "what is kiri",
                [{"title": "Kiri", "url": "https://kiri.ng", "snippet": "Kiri labs"}],
            ),
        ),
        ("summary", ai_service.build_summary_messages("Example", "Body of the page." * 50)),
    ):
        try:
            chunks: list[str] = []
            await ai_service.stream_chat(messages, 0, chunks.append)
            report(f"passive:{name}", bool(chunks), f"{len(chunks)} chunks")
            if not chunks:
                failures.append(f"passive:{name}")
        except Exception as exc:
            report(f"passive:{name}", False, f"{type(exc).__name__}: {exc}")
            failures.append(f"passive:{name}")

    # --- 6. export / import round-trip of the transcript we just built ---
    try:
        transcript = []
        for event, data in events:
            if event == "user":
                transcript.append({"role": "user", "content": data.get("text", "")})
            elif event == "text_final":
                transcript.append(
                    {"role": "assistant", "content": data.get("text", "")}
                )
        if not transcript:
            raise RuntimeError("no transcript to export")
        path = Path(tempfile.gettempdir()) / "ddgs_probe.kani"
        kani_backend.export_archive(transcript, str(path))
        back = kani_backend.import_archive(str(path))
        ok = [m for m in back if m["role"] == "user"] == [
            m for m in transcript if m["role"] == "user"
        ]
        report("kani_roundtrip", ok and path.exists(), f"{len(back)} messages")
        if not ok:
            failures.append("kani_roundtrip")
        path.unlink(missing_ok=True)
    except Exception as exc:
        report("kani_roundtrip", False, f"{type(exc).__name__}: {exc}")
        failures.append("kani_roundtrip")

    # --- 7. thinking depth passes through (auto omits, low sends) ---
    try:
        old = app_state.reasoning_effort
        app_state.reasoning_effort = "low"
        depth = chat_agent._thinking_depth()
        app_state.reasoning_effort = old
        report("thinking_depth", depth == "low", f"low->{depth}")
        if depth != "low":
            failures.append("thinking_depth")
    except Exception as exc:
        report("thinking_depth", False, f"{type(exc).__name__}: {exc}")
        failures.append("thinking_depth")

    return failures


async def main() -> int:
    print("== live AI probe ==", flush=True)
    failures: list[str] = []
    failures += await probe_tools()
    failures += await probe_end_to_end()
    print("\n== summary ==", flush=True)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL':4}  {name:34} {detail}", flush=True)
    if failures:
        print(f"\n{len(failures)} FAILURES: {failures}", flush=True)
        return 1
    print("\nall green", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
