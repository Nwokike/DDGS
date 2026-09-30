# anyio (+ sniffio) — Dependency Audit for DDGS

- **Version audited:** anyio 4.15.1, sniffio 1.3.1 (from `uv.lock`, verified in `.venv`)
- **Consumer status:** NEVER imported directly by DDGS today — verified: `grep -ri anyio|sniffio src/ tests/` returns nothing (exit 1). Rides transitively under `httpx==0.28.1` → `anyio`, and `openai==2.54.0` → `anyio + sniffio` (kani `[openai]` extra pulls `openai`). `pyproject.toml` does not declare it.
- **Backend in force:** asyncio-only. `BACKENDS = ("asyncio", "trio")`; trio backend (`_backends/_trio.py`) is installed but never selected here. Flet runs an asyncio loop; `sniffio.current_async_library()` returns `"asyncio"`.
- **DDGS async baseline (what it does instead today):** `asyncio.Event` for chat Stop (`chat_screen.py`), `asyncio.Lock` in `cache_service.py`/`credit_service.py`/`kani_backend.py`, `asyncio.create_task` / `asyncio.gather` for tool batches, `asyncio.wait_for(..., timeout)` for fetch timeouts (`agent_files.py`, `chat_agent.py`), raw `threading.Thread` + `threading.Lock` for the local router server (`ai_service.py`).

---

## 1. COMPLETE API INVENTORY

One line per public API (source: `anyio/__init__.py` + submodule signatures; anyio 4.15.1).

**Task groups — structured concurrency (`anyio.create_task_group()`, `abc.TaskGroup`)**
- `create_task_group() -> TaskGroup` — creates a group; `async with` body is the concurrency scope; `__aexit__` waits for ALL children and re-raises failures as `BaseExceptionGroup`. No fire-and-forget.
- `TaskGroup.start_soon(func, *args, name=None) -> TaskHandle` — spawns a coroutine now; returns handle (new in 4.14, replaces bare fire-and-forget).
- `TaskGroup.create_task(coro, name=None) -> TaskHandle` — lower-level spawn taking a coroutine object.
- `TaskGroup.start(func, *args, name=None) -> Any` — spawns a service task and blocks until it calls `task_status.started(value)`; returns the started value; raises if task exits without starting.
- `TaskGroup.cancel_scope: CancelScope` — every group owns a scope; `tg.cancel_scope.cancel()` cancels the whole group (the Stop-button primitive).
- `TaskHandle` — awaitable future for a spawned task: `.wait()`, `await handle` → return value, `.return_value` / `.exception` / `.status` (PENDING/FINISHED/CANCELLING/CANCELLED/FAILED), `.cancel()`, `.name`, `.coro`. Raises `TaskFailed`/`TaskCancelled`/`TaskNotFinished` on misuse.
- `TASK_STATUS_IGNORED` — no-op `TaskStatus` to pass when a `start()`-style callee requires a status object you don't care about.

**Cancel scopes & timeouts (`_core/_tasks.py`)**
- `CancelScope(*, deadline=math.inf, shield=False)` — sync context manager wrapping cancellable work; `.cancel(reason)`, `.deadline` (get/set clock value), `.cancel_called`, `.cancelled_caught` (True only if THIS scope caused the suppression — use to detect own timeout vs outer cancel), `.shield` (get/set).
- `CancelScope(shield=True)` — SHIELDING: inner block immune to outer cancellation (use to guarantee cleanup/persist/credit-settle runs even when Stop is pressed).
- `fail_after(delay, shield=False, reason=None)` — context manager that raises `TimeoutError` if block exceeds `delay` seconds; `None` disables.
- `fail_at(deadline, shield=False, reason=None)` — same but absolute clock deadline (new in 4.15.0).
- `move_on_after(delay, shield=False)` — same deadline mechanics but SILENTLY EXITS the block instead of raising (use for best-effort crawls); NOTE: timer starts at call time, not `__enter__` (changes in v5.0).
- `move_on_at(deadline, shield=False)` — absolute-clock silent variant (new in 4.15.0).
- `current_effective_deadline() -> float` — nearest deadline of all enclosing scopes (`inf` = none, `-inf` = already cancelled); useful for propagating remaining budget to httpx/primp calls.

**Memory object streams — back-pressured queues (`create_memory_object_stream`, `streams/memory.py`)**
- `create_memory_object_stream[T](max_buffer_size=0)` — returns `(MemoryObjectSendStream, MemoryObjectReceiveStream)`; `0` = rendezvous (handoff), `N` = buffered, `math.inf` = unbounded.
- `MemoryObjectSendStream` (PRODUCER) — `await send(item)` blocks when full (back-pressure); `send_nowait(item)` raises `WouldBlock` if full; `.clone()` for multi-producer; `.close()`/`.aclose()`; `statistics()`; raises `BrokenResourceError` if receivers all closed.
- `MemoryObjectReceiveStream` (CONSUMER) — `await receive()` blocks when empty; `receive_nowait()` raises `WouldBlock`/`EndOfStream`; `.clone()` for multi-consumer; `statistics()` → `MemoryObjectStreamStatistics(current_buffer_used, max_buffer_size, open_send/receive_streams, tasks_waiting_send/receive)`.

**Thread offload (`to_thread.py`)**
- `to_thread.run_sync(func, *args, abandon_on_cancel=False, limiter=None)` — runs sync callable (primp, lxml, sqlite, tokenizer) in a worker thread, awaits result without blocking the loop; `abandon_on_cancel=True` leaves thread running on cancel; `limiter` caps concurrency (default limiter = 40 threads).
- `to_thread.current_default_thread_limiter() -> CapacityLimiter` — the shared 40-token limiter; tune/inspect for download-parse fan-out.

**Sync↔async bridge (`from_thread.py`)**
- `BlockingPortal` — created INSIDE async context (`async with BlockingPortal()`); from any sync thread: `.call(func, *args)` (blocks thread, runs func/coroutine on loop, returns result), `.start_task_soon(func, *args, name=None) -> concurrent.futures.Future`, `.start(func, *args) -> (Future, started_value)`, `.wrap_async_context_manager(cm)` (use an async CM from sync code), `await portal.stop(cancel_remaining=...)`.
- `start_blocking_portal(backend="asyncio", backend_options=None)` — sync context manager that boots a FRESH event loop on a daemon thread and yields a portal (for Flet sync callbacks / `threading.Thread` workers that need to call async services).
- `BlockingPortalProvider(backend="asyncio", backend_options=None)` — ref-counted shared-portal manager; first thread in starts it, last out stops it.
- `from_thread.run(func, *args, token=None)` — call a COROUTINE from a worker thread, block for result (needs token outside AnyIO-spawned threads).
- `from_thread.run_sync(func, *args, token=None)` — call a SYNC func on the loop thread from a worker thread.
- `from_thread.check_cancelled()` — inside a `to_thread` worker, raise the loop's cancellation exception if the host task was cancelled (cooperative abort for long lxml loops).

**Sync primitives (`_core/_synchronization.py`)**
- `Event` — `set()`, `is_set()`, `await wait()`, `statistics()`; constructible OUTSIDE a running loop (lazy adapter) — safe as a module-level Stop flag, unlike `asyncio.Event`.
- `Lock(*, fast_acquire=False)` — `await acquire()`, `acquire_nowait()` (raises `WouldBlock`), `release()`, `locked()`, async-CM, `statistics()`; loop-lazy like Event.
- `Semaphore(initial_value, *, max_value=None, fast_acquire=False)` — `await acquire()`, `acquire_nowait()`, `release()`, `.value`, `.max_value`, async-CM, `statistics()`; the crawl-concurrency cap (N parallel fetches).
- `Condition(lock=None)` — backend-independent condition: `await acquire()/acquire_nowait()/wait()`, `notify(n=1)`/`notify_all()`, `wait_for(predicate)` (new 4.11), `statistics()`; reacquires lock under shield on wake.
- `CapacityLimiter(total_tokens)` — token pool: `await acquire()/acquire_on_behalf_of(borrower)`, `*_nowait`, `release()/release_on_behalf_of`, read-write `.total_tokens`, `.borrowed_tokens`, `.available_tokens`, async-CM, `statistics()`.
- `ResourceGuard(action="using")` — sync CM raising `BusyResourceError` if re-entered (single-task resource protection).

**Byte/object streams & adapters (`abc/_streams.py`, `streams/buffered.py|text.py|stapled.py|tls.py|file.py`)**
- `ByteReceiveStream` — `await receive(max_bytes=65536) -> bytes`, async-iterable; `ByteSendStream` — `await send(bytes)`; `ByteStream` — both + `send_eof()`; `Listener.serve(handler)` + `MultiListener`.
- `ObjectReceiveStream[T]/ObjectSendStream[T]/ObjectStream[T]` — typed `receive() -> T` / `send(T)` / `send_eof()` object variants.
- `BufferedByteReceiveStream` — `feed_data()`, `receive_exactly(n)`, `receive_until(delimiter, max_bytes)` (raises `IncompleteRead`/`DelimiterNotFound`); `BufferedByteStream`, `BufferedConnectable`.
- `TextReceiveStream/TextSendStream/TextStream(encoding, errors)` — bytes↔str decode/encode wrappers; `TextConnectable`.
- `StapledByteStream(send_stream, receive_stream)` / `StapledObjectStream` — glue a send-half and receive-half into one stream; `FileReadStream.from_path()/receive()/seek()/tell()`, `FileWriteStream.from_path()/send()`.
- `TLSStream.wrap(...)` / `TLSListener` / `TLSConnectable` — TLS over any byte stream (httpx uses its own, but direct-TLS crawlers could use this).
- `AsyncFile` / `open_file(...)` / `wrap_file(fp)` (`_core/_fileio.py`) — async file with awaitable read/write/seek/flush + async iteration; BinaryIO adapter for downloads-to-disk without blocking the loop.
- `Path(*args, limiter=None)` — async `pathlib.Path` mirror; every I/O method awaited (`read_bytes`, `write_bytes`, `stat`, `glob`/`rglob`/`iterdir` async iterators, `mkdir`, `unlink`, …).

**Concurrency helpers (`_core/_concurrency_utils.py`)**
- `gather(*coros) -> tuple` — run coroutines in a task group, results in ARGUMENT order (structured replacement for `asyncio.gather`).
- `as_completed(*awaitables)` — async-CM yielding a receive stream of `TaskHandle`s in COMPLETION order (first-finished-result UI updates).
- `amap(func, args) -> list` — run coroutine-func over args concurrently, ordered results (engine fan-out one-liner).

**Event loop / clock (`_core/_eventloop.py`)**
- `run(func, *args, backend="asyncio", backend_options=None)` — blocking entry point; refuses if a loop already runs in this thread.
- `sleep(delay)` / `sleep_forever()` / `sleep_until(deadline)` — cancellable sleeps (crawl backoff/polling).
- `current_time() -> float` — loop monotonic clock (deadline arithmetic).
- `get_all_backends()` → `("asyncio", "trio")`; `get_available_backends()` → importable subset; `get_cancelled_exc_class()` → backend's cancel exception (`asyncio.CancelledError` on our backend).

**Low-level checkpoints & tokens (`lowlevel.py`)**
- `checkpoint()` — cancellation point + scheduler yield; `checkpoint_if_cancelled()` — cancel check only; `cancel_shielded_checkpoint()` — yield without cancel check.
- `current_token() -> EventLoopToken` / `EventLoopToken(backend_class, native_token)` — opaque loop handle for cross-thread calls (4.11+).
- `RunVar(name, default)` + `RunvarToken` — loop-scoped variable (like ContextVar but per running loop); `.get/.set/.reset`, usable as CM.

**Testing helpers (`_core/_testing.py`)**
- `TaskInfo(id, parent_id, name, coro)` + `has_pending_cancellation()` — task introspection.
- `get_current_task() -> TaskInfo` / `get_running_tasks() -> list[TaskInfo]` — who is running (deadlock diagnosis).
- `wait_all_tasks_blocked()` — waits until all other tasks are parked; NOTE: there is NO `wait_all_tasks_completed` — completion-waiting is expressed by exiting the `async with task_group:` block.
- `Future` (`_core/_futures.py`) — anyio-native future with PENDING/FINISHED/CANCELLING/CANCELLED/FAILED status, `return_value`/`exception` setters mirroring TaskHandle semantics.

**Files / processes / sockets / misc**
- `open_process(...)` / `run_process(...)` — async subprocesses (`abc/_subprocesses.py`: `Process` with stdin/stdout/stderr streams, `aclose`, `wait`, `terminate`, `kill`, `send_signal`).
- `connect_tcp(...)` / `create_tcp_listener(...)` / `connect_unix` / UDP + unix-datagram creators / `getaddrinfo` / `getnameinfo` / `wait_readable/writable` / `wait_socket_readable/writable` / `notify_closing` (`_core/_sockets.py` + `abc/_sockets.py`: `SocketStream`, `SocketListener`, `UDPSocket`, `ConnectedUDPSocket`, `UNIXDatagramSocket`).
- `open_signal_receiver(*signals)` — async CM yielding a stream of received signals.
- `TemporaryFile/NamedTemporaryFile/SpooledTemporaryFile/TemporaryDirectory/mkstemp/mkdtemp/gettempdir/gettempdirb` — async `tempfile` mirror (download staging).
- `aclose_forcefully(resource)` — close even if already closing; `typed_attribute()/TypedAttributeSet/TypedAttributeProvider` — typed `extra()` metadata on streams/sockets; `AsyncContextManagerMixin/ContextManagerMixin` — mixin base for custom resources.
- `to_process.run_sync(...)` / `current_default_process_limiter()` — run func in worker PROCESS; `to_interpreter.run_sync(...)` — run func in sub-INTERPRETER (3.14+ / experimental).
- `functools.cache/lru_cache` (async-aware LRU) / `itertools` async helpers — memoize coroutine functions (tokenizer/model-metadata caches).
- `abc.AsyncBackend` / `abc.TestRunner` / `abc.AsyncResource` — backend & resource interfaces (only relevant if writing a custom backend).

**pytest plugin (`pytest_plugin.py`)**
- `@pytest.mark.anyio` + `anyio_backend` fixture (module-scoped, parametrized over `get_available_backends()`) — runs each marked coroutine test once per backend; override locally with `@pytest.fixture def anyio_backend(): return "asyncio"` to pin asyncio-only and halve CI.
- `anyio_backend_name` / `anyio_backend_options` fixtures — unpack the (name, options) tuple form.
- `anyio_mode` ini/flag (`strict` default vs `auto`) — auto runs ALL async tests under anyio (warns if combined with pytest-asyncio auto mode).
- `free_tcp_port` / `free_udp_port` / `free_tcp_port_factory` / `free_udp_port_factory` fixtures — race-free ephemeral ports for router/listener tests.

**sniffio (3 files: `__init__.py`, `_impl.py`, `_version.py`)**
- `current_async_library() -> str` — `"asyncio"` inside Flet/httpx/openai calls; raises `AsyncLibraryNotFoundError` outside a loop — the canonical "which loop am I on?" probe.
- `current_async_library_cvar: ContextVar` — the context var carrying the above; anyio sets/resets it around `run()`.
- `AsyncLibraryNotFoundError` — catch to detect sync context (e.g. Flet sync callback) and route to portal/thread path.
- `thread_local` — threading-local fallback storage when no event loop context exists.

**Exceptions (`_core/_exceptions.py`)**
- `EndOfStream` (peer closed), `ClosedResourceError` (used after close), `BrokenResourceError` (peer gone — catch on send), `WouldBlock` (nowait miss), `BusyResourceError` (ResourceGuard re-entry), `DelimiterNotFound/IncompleteRead` (buffered reads), `ConnectionFailed(OSError)`, `NoEventLoopError`, `RunFinishedError` (portal token dead), `BrokenWorkerProcess/BrokenWorkerInterpreter`, `TypedAttributeLookupError`, `TaskFailed/TaskCancelled/TaskNotFinished`, `FutureFailed/FutureCancelled/FutureNotFinished/FutureAlreadyFinished`, `iterate_exceptions(exc)` (flatten ExceptionGroups).

---

## 2. LATENT CAPABILITIES FOR DDGS (ranked by UX impact)

1. **`to_thread.run_sync` for primp + lxml — kill the UI freezes.** Highest impact. `media_downloader.py`/`youtube/innertube_client.py` run sync `primp` and `agent_files.py` runs sync `lxml` parses today; anything slow blocks the Flet loop and freezes chat/downloads. Wrap: `html = await to_thread.run_sync(primp_client.get, url)` / `tree = await to_thread.run_sync(lxml.html.fromstring, html)` with a shared `CapacityLimiter(8)` so a crawl burst cannot spawn 40 threads. `abandon_on_cancel=True` for parse jobs the user cancelled.
2. **Memory object streams for chat tokens → renderer + download progress.** Replace ad-hoc `asyncio.Queue`/callback chains: producer task `await send_stream.send(token_chunk)` with `max_buffer_size=64` gives NATURAL back-pressure (fast model throttles instead of OOMing the UI); renderer consumes `async for chunk in recv`. Same pair carries `(bytes_done, total)` progress events from `download_media` to the progress bar. `statistics()` exposes queue depth for a "buffered…" indicator. Multi-consumer `.clone()` fans one crawl result to chat + cache + log.
3. **Task groups for the scheduled-crawl engine + chat tool fan-out.** `chat_agent._dispatch` / `kani_backend` tool batches use `asyncio.gather` (first exception cancels silently-ish, no scope). `async with create_task_group() as tg: tg.start_soon(fetch, url) ...` gives fan-out fetches with ONE cancel handle, ordered `gather()` replacement, or `as_completed()` for first-result-wins UI. Exiting the block = all children done — the "crawl round finished" barrier for free.
4. **`fail_after` wrapping flaky tool calls.** `agent_files.extract_url` / `_dispatch` steps use `asyncio.wait_for` (cancels the whole task, awkward to shield). `with fail_after(20, reason="engine fetch"): ...` raises catchable `TimeoutError` scoped to the fetch only; `move_on_after(10)` for best-effort enrichment (thumbnail fetch fails → skip, don't fail the turn). `current_effective_deadline()` propagates remaining budget into nested httpx calls.
5. **Cancel scopes for real Stop-button semantics.** `chat_screen.cancel = asyncio.Event()` is cooperative-polling. `with CancelScope() as scope: ... scope.cancel("user pressed Stop")` cancels the turn's task tree IMMEDIATELY; check `scope.cancelled_caught` to distinguish user-Stop ("Stopped." message) from timeout/error. Wrap credit-settle/persist in `with CancelScope(shield=True):` so Stop never skips charging logic (`credit_service._auto_rollback`, `chat_agent.settle_turn`).
6. **`BlockingPortal` for Flet sync callbacks calling async services.** Flet `on_click`/`on_tap_link` handlers are sync; today they do `asyncio.create_task(...)` (loses exceptions, races loop state). A single app-lifetime `start_blocking_portal("asyncio")` (or `BlockingPortalProvider`) lets sync handlers do `portal.call(chat_agent.run_turn, ...)` and get the result/exception back synchronously. Also the clean bridge for the `threading.Thread(server.serve_forever)` router in `ai_service.py` to call back into async code.
7. **`Event`/`Semaphore`/`Condition` drop-ins that work outside the loop.** `anyio.Event/Semaphore` can be constructed at module import (lazy adapter); `asyncio.Event()` cannot (binds loop). Fixes import-order crashes for the global cancel event and gives crawl-parallelism cap: `Semaphore(4)` around engine fetches. `Condition.wait_for(pred)` for approval dialogs (`chat_screen._confirm`) instead of hand-rolled event+dict.
8. **Async file/Path/tempfile for downloads + cache.** `AsyncFile`/`open_file`/`wrap_file` + `Path.write_bytes/read_bytes` move `media_downloader` disk writes and `cache_service`/`storage_service` persistence off the loop thread; `TemporaryDirectory` for atomic download-staging-then-rename. Same limiter family as (1).
9. **`gather`/`amap`/`as_completed` one-liners.** Replace `asyncio.gather` in `kani_backend` tool batches with `amap(run_tool, calls)` (ordered) or `as_completed` (stream first-finishing tool result to UI). Less code, structured errors.
10. **pytest plugin + testing hooks for the chat/crawl suite.** Pin `anyio_backend = "asyncio"` fixture + `@pytest.mark.anyio` for `run_turn`/`settle_turn` timeout tests; `wait_all_tasks_blocked()` to flush background persist tasks before asserting; `get_running_tasks()` to debug leaked crawl tasks; `free_tcp_port` for the embedded router tests. Low UX impact, high contributor-velocity impact.

Suggested first diff (no new dependency — already installed): `to_thread.run_sync` around primp/lxml + `fail_after` around `extract_url` + `CancelScope` for chat Stop. All three compose inside the existing asyncio loop with zero backend change.

---

## 3. GOTCHAS

- **asyncio-only; never touch the trio backend.** `run(backend="trio")`, `BlockingPortalProvider(backend="trio")`, and parametrized `anyio_backend` (asyncio+trio) will all break Flet, which owns an asyncio loop. Always pass Pin `anyio_backend` to `"asyncio"` in tests; pass `backend="asyncio"` explicitly to `run`/`start_blocking_portal`.
- **Interop with plain asyncio is fine but scoped.** Inside a running asyncio loop, anyio primitives (`Event`, `Lock`, `Semaphore`, `to_thread.run_sync`, `create_task_group`, `sleep`) work directly. Do NOT mix `asyncio.gather/wait_for/create_task` INSIDE an anyio task group and expect group cancellation to propagate — use `tg.start_soon` + `fail_after`. Do NOT call `anyio.run()` from inside a running loop (raises RuntimeError); from Flet sync callbacks use `portal.call()`, not `anyio.run()`.
- **Exception groups WILL bite.** Task-group `__aexit__` raises `BaseExceptionGroup`, not the first exception. `except Exception` still catches `ExceptionGroup` (it subclasses), but `except TimeoutError`/`except httpx.HTTPError` around a whole `async with create_task_group` block will MISS errors wrapped in the group. Either catch per-child inside the child func, or flatten with `anyio.iterate_exceptions(eg)` / `except* HTTPError`. This is the #1 migration bug from `asyncio.gather` (which returns exceptions by default) — audit `kani_backend._raise_mapped` and `chat_agent._error_text` before wrapping tool batches in a group.
- **Cancellation ≠ TimeoutError.** `move_on_after/fail_after` and `scope.cancel()` raise the backend's cancellation exception (`asyncio.CancelledError`, via `get_cancelled_exc_class()`), which `fail_after` converts to `TimeoutError` ONLY on scope exit. `CancelledError` inherits `BaseException`, so bare `except Exception` in tool code will NOT swallow it (good) — but `finally` + shielded cleanup is still required for credit/persist paths.
- **`move_on_after` timer starts at CALL, not ENTER** (until v5.0): `scope = move_on_after(10)` then `await slow_setup(); with scope:` already burned budget. Prefer constructing it immediately before `with`, or use `fail_after` (contextmanager form, timer starts on enter).
- **Memory-stream lifecycle warnings.** Unclosed send/receive clones emit `ResourceWarning`; receivers get `EndOfStream` only after ALL send clones close — use `async with send:` / `async with recv:` or explicit `.close()`. `send_nowait` on a zero-buffer stream with no waiter raises `WouldBlock` — normal, not a bug.
- **Why openai/httpx require it (do not remove).** `httpx` uses anyio for its backend-agnostic transport (`AsyncClient` runs identically on asyncio/trio via anyio streams/sockets/task groups); `openai` builds its async client/retries/SSE on top of httpx+anyio and uses `sniffio.current_async_library()` to detect the running loop. Removing anyio/sniffio breaks `import httpx`, `import openai`, and therefore `kani[openai]` — i.e. the entire chat engine. They are load-bearing transitives, which is exactly why using them directly costs nothing.
- **Threading edge cases.** `to_thread.run_sync` default cap is 40 threads — bound crawl fan-out with an explicit `CapacityLimiter`. `from_thread.run/run_sync` outside AnyIO-spawned threads REQUIRES the portal token. `check_cancelled()` only works inside `to_thread` workers. `to_process` (fork) is unreliable on Windows/Android — prefer threads; `to_interpreter` needs 3.14+ subinterpreters — not for this app.

---

## 4. COVERAGE

- **Files read / total: 49 / 49 (anyio 46 + sniffio 3).**
- Full reads (15): `anyio/__init__.py`, `_core/_tasks.py`, `_core/_synchronization.py`, `_core/_eventloop.py`, `_core/_exceptions.py`, `_core/_concurrency_utils.py`, `_core/_streams.py`, `_core/_testing.py`, `_core/_fileio.py`, `to_thread.py`, `from_thread.py`, `lowlevel.py`, `pytest_plugin.py`, `streams/memory.py`, `sniffio/__init__.py`.
- Signature-level greps (34): `abc/_tasks.py`, `abc/_streams.py`, `abc/_eventloop.py`, `abc/_resources.py`, `abc/_sockets.py`, `abc/_subprocesses.py`, `abc/_testing.py`, `streams/buffered.py`, `streams/text.py`, `streams/stapled.py`, `streams/tls.py`, `streams/file.py`, `_core/_sockets.py`, `_core/_subprocesses.py`, `_core/_tempfile.py`, `_core/_signals.py`, `_core/_futures.py`, `_core/_resources.py`, `_core/_typedattr.py`, `_core/_contextmanagers.py`, `to_process.py`, `to_interpreter.py`, `functools.py`, `itertools.py`, `_backends/_asyncio.py`, `_backends/_trio.py`, `_backends/__init__.py`, `_core/__init__.py`, `abc/__init__.py`, `streams/__init__.py`, `_lazyimport.py`, `sniffio/_impl.py`, `sniffio/_version.py`, plus `uv.lock` (anyio 4.15.1 / sniffio 1.3.1 / httpx+openai edges) and `src/` usage grep (zero direct imports; asyncio/threading patterns catalogued).
- Not executed: no runtime probe beyond version import; backend behavior taken from source. Trio backend inventoried, explicitly out of scope for DDGS.
