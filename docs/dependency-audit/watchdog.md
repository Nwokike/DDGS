# watchdog 6.0.0 — Dependency Audit for DDGS

**Status: 0% utilized — pure transitive dependency.** DDGS never imports
`watchdog`. `uv.lock` shows it is pulled in only as a dependency of
`flet_cli 1.0.1` (which uses it for `flet run --watch` hot-reload during
development). The two `*watchdog*` hits in `src/` (`app_controller.py`
`_router_watchdog`, `ai_service.py` status watchdog) are hand-rolled asyncio
polling loops, unrelated to this package. Everything below is latent.

## 1. COMPLETE API INVENTORY

- `Observer` (`observers/__init__.py`) — factory alias, picks native backend per platform (Inotify/Linux, FSEvents/macOS, Kqueue/BSD, WinApi/Windows, Polling fallback), constructed as `Observer(timeout=1.0)`.
- `BaseObserver.schedule(handler, path, recursive=False, event_filter=[...])` — attaches a handler to a path, spawns one emitter thread per watch, returns an `ObservedWatch`.
- `BaseObserver.unschedule(watch)` / `unschedule_all()` — detach watch(es), stop and join their emitter threads.
- `BaseObserver.start()` / `stop()` (via `EventDispatcher`) — starts dispatcher + all emitters; `stop()` injects a `stop_event` sentinel into the queue; `start()` after `stop()` is not reusable (threads are one-shot).
- `BaseObserver.add_handler_for_watch()` / `remove_handler_for_watch()` — add/remove handlers on a live watch without touching the emitter.
- `ObservedWatch` — value object keyed on `(path, recursive, event_filter)`; `event_filter` is a list of event classes to emit (server-side filtering at `queue_event` time).
- `EventEmitter` — producer `BaseThread` per watch, loops `queue_events(timeout)`; `timeout` doubles as poll interval for polling emitters.
- `EventDispatcher.dispatch_events()` — consumer loop: blocking `queue.get`, fans out to all handlers registered for that watch (copy-on-read, so handlers may unschedule themselves safely).
- NOTE: there is **no** `schedule_non_recursive` in v6.0.0 — non-recursive is just `schedule(..., recursive=False)` (default).
- `EventQueue(SkipRepeatsQueue)` — drops a `put` identical to the last item queued, coalescing back-to-back duplicate events before dispatch.
- `FileSystemEvent` — immutable dataclass (`src_path`, `dest_path=""`, `event_type`, `is_directory`, `is_synthetic`), hashable, usable as dict key/set member.
- `FileCreatedEvent` / `FileModifiedEvent` / `FileDeletedEvent` / `FileMovedEvent(src,dest)` (`event_type` created/modified/deleted/moved) — file-level events.
- `DirCreatedEvent` / `DirModifiedEvent` / `DirDeletedEvent` / `DirMovedEvent` (`is_directory=True`) — directory-level events.
- `FileClosedEvent` / `FileClosedNoWriteEvent` / `FileOpenedEvent` — close-after-write (signals download completion), close-without-write, open; Linux/inotify only in practice.
- `generate_sub_moved_events(src, dest)` / `generate_sub_created_events(path)` — synthesize per-file events for everything under a moved/created dir (used by WinApi emitter).
- `FileSystemEventHandler.dispatch(event)` — calls `on_any_event(event)` then `on_{event_type}(event)`; override `on_created/on_modified/on_deleted/on_moved/on_closed/on_closed_no_write/on_opened`.
- `PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive=False)` — glob filtering via `pathlib.PurePath.match` on both src and dest paths; properties are read-only.
- `RegexMatchingEventHandler(regexes default [r".*"], ignore_regexes, ignore_directories, case_sensitive)` — precompiles `re` patterns (`re.IGNORECASE` unless case-sensitive); `match()` (not `search()`) against src+dest paths; compiled patterns exposed read-only so callers can inspect `.pattern` / use `.groups()` from their own match.
- `LoggingEventHandler(logger=None)` — logs every event at INFO; drop-in diagnostics tracer.
- `PollingObserver` / `PollingEmitter` — backend-agnostic fallback: snapshots the tree (`DirectorySnapshot`) every `timeout` seconds, diffs it (`DirectorySnapshotDiff` by inode+mtime+size), synthesizes create/modify/delete/move events.
- `PollingObserverVFS(stat, listdir, polling_interval)` — same polling engine against a *virtual* filesystem (custom stat/listdir callables), e.g. watching inside archives or remote listings.
- `DirectorySnapshot` / `DirectorySnapshotDiff` / `EmptyDirectorySnapshot` (`utils/dirsnapshot.py`) — one-shot tree snapshot and set-diff usable *without* any observer thread (`snapshot2 - snapshot1` operator, `ContextManager` helper); move detection is inode-based so cross-partition moves degrade to delete+create.
- `EventDebouncer(debounce_interval_seconds, events_callback)` (`utils/event_debouncer.py`) — background thread that batches bursts: resets its timer on each new event, delivers the ordered list once quiet.
- `DelayedQueue(delay)` (`utils/delayed_queue.py`) — queue where items `put(..., delay=True)` are held `delay` seconds and can be `remove(predicate)`d before delivery (cancellable coalescing window).
- `filter_paths` / `match_any_paths` (`utils/patterns.py`) — standalone glob include/exclude matchers; case-insensitive mode lowercases and uses `PureWindowsPath` semantics.
- `Trick` / `LoggerTrick` / `ShellCommandTrick` / `AutoRestartTrick` (`tricks/__init__.py`) — YAML-configurable `PatternMatchingEventHandler` subclasses: log events, run a `${watch_src_path}`-templated shell command (with `wait_for_process`/`drop_during_process` anti-storm flags), or supervise+restart a subprocess with SIGINT→SIGKILL escalation and optional debouncing.
- `watchmedo` CLI (`watchmedo.py`) — `log` (print events, `-p` patterns `-i` ignores `-R` recursive `--timeout`), `shell-command` (event→shell), `auto-restart` (event→restart subprocess, `--debounce-interval`), `tricks-from` (YAML file), `generate-tricks-yaml`; `--debug-force-{polling,kqueue,winapi,fsevents,inotify}` backend overrides.
- `BaseThread` (`utils/__init__.py`) — daemon-by-default stoppable `threading.Thread` with `should_keep_running()` / `stop()` / `on_thread_start|stop()` hooks; every observer/emitter/debouncer is one.
- `ProcessWatcher` (`utils/process_watcher.py`) — thread that fires a callback when a `Popen` exits (used by tricks to detect crashes).
- `platform` (`utils/platform.py`) — `is_linux/is_darwin/is_bsd/is_windows`; anything else (incl. **Android/iOS**) is `PLATFORM_UNKNOWN` → `Observer` silently becomes `PollingObserver`.
- `version.py` — `VERSION_STRING = "6.0.0"`, `VERSION_INFO` tuple.
- Backends (`inotify.py` + `inotify_buffer.py` + `inotify_c.py` / `kqueue.py` / `fsevents.py` + `fsevents2.py` / `read_directory_changes.py` + `winapi.py`) — per-OS emitter implementations behind the `Observer` factory; only `WindowsApiObserver` (ReadDirectoryChangesW) runs on DDGS's Windows target.

## 2. LATENT CAPABILITIES FOR DDGS (ranked)

1. **Live log tail for the Activity/diagnostics terminal** — `Observer.schedule(handler, log_dir, recursive=False, event_filter=[FileModifiedEvent])` + `on_modified` re-reads only the appended bytes of `app_<ts>.log`; replaces polling the file and gives true `tail -f` behavior. Caveat: `RotatingFileHandler` rotation shows up as delete+create, so handle `FileCreatedEvent` by reopening the handle.
2. **Auto-refresh the downloads list when files land on disk** — schedule a watch on the save directory (`_resolve_save_path` target in `components/results/downloader.py`); `on_created` inserts the row, `FileClosedEvent` (Linux) or a small `EventDebouncer` marks completion — no manual refresh button needed.
3. **Hot-reload the `engine_local.py` cache when upstream changes** — `engine.py` writes `cache_dir()/engine_local.py` via a `.new.py` + replace; today a new fetch requires restart to take effect. Watching the cache dir for `FileModifiedEvent` on `engine_local.py` enables in-place module reload.
4. **External `settings.json` edits reflected live** — a `PatternMatchingEventHandler(patterns=["settings.json"])` on the data dir (`core/storage_paths.data_dir()`) lets users/scripts tweak config without an app restart; `ignore_directories=True` keeps it file-only.
5. **Pattern matching for `*.part`/`.new.py` temp files during downloads** — `ignore_patterns=["*.part", "*.new.py", "*.tmp"]` (downloader writes + `engine.py`'s `.new.py` staging) prevents half-written files from triggering refresh/reload handlers prematurely.
6. **Event coalescing/debounce for download bursts** — `EventQueue/SkipRepeatsQueue` already dedupes back-to-back identical events for free; layering `EventDebouncer` (batch → single UI refresh) or `DelayedQueue` (cancellable window) in front of the UI update path prevents a 50-file batch from issuing 50 list rebuilds.
7. **`PollingObserverVFS` for virtual/remote listings** — if DDGS ever watches non-local content (router feed, `version.json`/update feed), custom `stat`/`listdir` callables give diff-events with zero new code.
8. **`DirectorySnapshotDiff` for cheap one-shot change checks** — `version.json`/update-feed polling or "what changed since last launch" needs no persistent thread: snapshot, compare, act.
9. **`AutoRestartTrick` pattern for supervised subprocesses** — debounced restart + SIGINT→SIGKILL escalation is a ready-made template if DDGS ever supervises a sidecar process.
10. **`watchmedo log` as a zero-code debug tool** — `uv run watchmedo log -R <dir>` traces filesystem activity during download/settings bug investigations without writing code.

## 3. GOTCHAS

- **Android/iOS = silent polling fallback.** `platform.py` knows only linux/darwin/bsd/windows; mobile targets resolve to `PLATFORM_UNKNOWN` and `Observer` degrades to `PollingObserver`, which full-tree-scans every `timeout` seconds — battery and I/O cost scale with tree size, so scope watches narrowly and raise the interval on mobile.
- **Event storms on downloads.** A single save fires created + N×modified (+ temp-file events); never rebuild UI per event — rely on the built-in `SkipRepeatsQueue` dedupe *plus* an `EventDebouncer`/batching layer before touching Flet controls.
- **Thread lifecycle.** Every observer/emitter is a daemon `BaseThread`: call `observer.stop()` + `observer.join()` on app exit (missing `stop()` leaks the emitter until interpreter teardown); Flet callbacks run on the UI thread, so marshal handler → `page.run_task`/pubsub rather than mutating controls from the emitter thread.
- **Windows path case-sensitivity.** `PatternMatchingEventHandler(case_sensitive=False)` (the default) lowercases via `PureWindowsPath` semantics — `*.LOG` matches `app.log`; setting `case_sensitive=True` on Windows silently narrows matches. Keep the default on Windows.
- **`schedule()` has no non-recursive variant name** — `recursive=False` is the default; passing no flag already limits to the top level (there is no `schedule_non_recursive` in v6.0.0 despite older docs/snippets suggesting one).
- **Close events are Linux-only in practice** — `FileClosedEvent` (the clean "download finished" signal) comes from inotify; on Windows (`WindowsApiObserver`) only create/modify/delete/move arrive, so completion detection needs the debounce heuristic there.
- **Move detection breaks across partitions** — snapshot/inode-based move inference degrades to delete+create pairs when files cross filesystems; don't assume `dest_path` is populated for moves onto another drive.

## 4. COVERAGE

**25 / 25 .py files read** (17 full reads: `events.py`, `observers/api.py`, `observers/__init__.py`, `observers/polling.py`, `tricks/__init__.py`, `watchmedo.py`, `version.py`, `__init__.py`, all 9 `utils/*`; 8 skimmed at class/method level: `inotify.py`, `inotify_buffer.py`, `inotify_c.py`, `kqueue.py`, `fsevents.py`, `fsevents2.py`, `read_directory_changes.py`, `winapi.py`). Consumer grep over `src/` + `uv.lock` + `pyproject.toml` confirms zero direct imports ��� `flet_cli 1.0.1` is the sole puller (`flet run --watch`).
