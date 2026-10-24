# Codex Supervisor Terminal Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw JSON and repeated dashboard dumps with a width-aware dashboard and a strictly read-only, human-readable worker conversation stream.

**Architecture:** Add a pure `presentation.py` module for Unicode-safe terminal formatting and event rendering, plus a small `jsonl_tail.py` module that follows complete UTF-8 JSONL records without writing to the log. Keep process/session behavior in the existing runner and state store unchanged; `cli.py` only orchestrates reads, rendering, and interactive screen refresh.

**Tech Stack:** Python 3.11 standard library, PowerShell 5.1-compatible wrappers, pytest.

## Global Constraints

- Observation is strictly read-only: never call start, resume, stop, accept, `append_event`, or a Codex session write API from `watch` or `dashboard`.
- Preserve the existing public CLI, `--once`, `--tail`, PowerShell entry points, event JSONL, state JSON, and final-result schema.
- Do not add third-party dependencies; Unicode width handling uses `unicodedata`.
- Do not fabricate timestamps or durations because existing events do not contain reliable time fields.
- Successful command output stays collapsed; failed commands show only the final meaningful error line.
- Interactive dashboard watch may refresh in place; non-TTY output and one-shot commands contain no cursor-control sequences.
- Keep unrelated dirty-worktree files untouched and stage only files named by the current task.

---

## File Structure

- Create `src/codex_supervisor/presentation.py`: display-width primitives, dashboard renderer, state/status labels, task rendering, Codex event rendering, command and failure summaries.
- Create `src/codex_supervisor/jsonl_tail.py`: complete-line initial tail and incremental follower with partial-line and truncation handling.
- Modify `src/codex_supervisor/cli.py`: route dashboard and watch data through the new modules and perform TTY-aware refresh.
- Modify `scripts/codex-supervisor/Watch-Worker.ps1`: expose the existing tail count as an optional validated parameter while preserving observer-only semantics.
- Modify `tests/test_codex_supervisor_cli.py`: integration expectations for human-readable watch output and non-TTY dashboard output.
- Create `tests/test_codex_supervisor_presentation.py`: pure formatter and width-layout tests.
- Create `tests/test_codex_supervisor_jsonl_tail.py`: complete-line, append, partial-line, and truncation tests.
- Modify `tests/test_codex_supervisor_powershell.py`: executed-argument contract for the optional tail parameter and existing safety checks.
- Modify `docs/codex/cli-supervisor-runbook.md`: document the readable stream, compact dashboard, width fallback, and strict read-only guarantee.

---

### Task 1: Unicode-Safe Display Primitives and Dashboard Renderer

**Files:**
- Create: `src/codex_supervisor/presentation.py`
- Create: `tests/test_codex_supervisor_presentation.py`

**Interfaces:**
- Produces: `display_width(text: str) -> int`
- Produces: `truncate_display(text: str, width: int) -> str`
- Produces: `compact_count(value: int) -> str`
- Produces: `render_dashboard(states: Mapping[str, Mapping[str, Any]], branches: Mapping[str, str], width: int, refreshed_at: str | None = None) -> str`
- Consumes: public worker-state dictionaries returned by `WorkerState.to_public_json()`.

- [ ] **Step 1: Write failing primitive tests**

Name the breaks: naïve `len()` splits/widens Chinese text incorrectly; token formatting produces unreadable full integers or unstable rounding.

```python
from src.codex_supervisor.presentation import (
    compact_count,
    display_width,
    truncate_display,
)


def test_display_width_counts_chinese_as_two_columns() -> None:
    assert display_width("A失败") == 5
    assert truncate_display("投影线程很长", 7) == "投影线…"
    assert display_width(truncate_display("投影线程很长", 7)) <= 7


@pytest.mark.parametrize(
    ("value", "expected"),
    [(999, "999"), (1_200, "1.2K"), (246_655_468, "246.7M"),
     (2_347_311_773, "2.35B")],
)
def test_compact_count_uses_stable_terminal_units(
    value: int, expected: str
) -> None:
    assert compact_count(value) == expected
```

- [ ] **Step 2: Run primitive tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'src.codex_supervisor.presentation'`.

- [ ] **Step 3: Implement the minimal Unicode and count primitives**

Use `unicodedata.combining()` and `unicodedata.east_asian_width()`; combining marks add zero columns, `W`/`F` add two, all other code points add one. `truncate_display` reserves one display column for `…` and never returns a dangling combining mark. `compact_count` chooses the largest applicable unit and formats at most four visible significant characters before the suffix.

```python
def display_width(text: str) -> int:
    return sum(_character_width(character) for character in text)


def truncate_display(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    target = width - 1
    result: list[str] = []
    used = 0
    for character in text:
        char_width = _character_width(character)
        if used + char_width > target:
            break
        result.append(character)
        used += char_width
    return "".join(result).rstrip() + "…"
```

- [ ] **Step 4: Run primitive tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: all primitive tests pass.

- [ ] **Step 5: Write failing dashboard layout tests**

Name the breaks: a missing responsive branch recreates overlapping/wrapped columns; wrong usage arithmetic omits reasoning tokens; repeated `codex/` wastes width.

```python
def _states() -> dict[str, dict[str, object]]:
    return {
        "A": {
            "worker": "A", "phase": "planning",
            "status": "completed_pending_review",
            "tests_summary": "409 passed, 3 warnings in 8.86s",
            "usage": {"input_tokens": 200_000_000,
                      "output_tokens": 40_000_000,
                      "reasoning_output_tokens": 6_655_468,
                      "cached_input_tokens": 231_070_976},
        },
        "B": {"worker": "B", "phase": "planning", "status": "failed",
              "tests_summary": "213 passed, 3 warnings in 139.09s",
              "usage": {}},
        "C": {"worker": "C", "phase": "-", "status": "not_started",
              "tests_summary": "-", "usage": {}},
    }


def test_wide_dashboard_has_one_bounded_row_per_worker() -> None:
    rendered = render_dashboard(
        _states(),
        {"A": "codex/rag-a-routing", "B": "codex/rag-b-bm25",
         "C": "codex/rag-c-projection"},
        width=120,
        refreshed_at="14:32:08",
    )
    lines = rendered.splitlines()
    assert "rag-a-routing" in rendered
    assert "codex/" not in rendered
    assert "246.7M" in rendered
    assert "231.1M" in rendered
    assert any("待审核" in line for line in lines)
    assert all(display_width(line) <= 120 for line in lines)


def test_narrow_dashboard_uses_two_lines_per_worker() -> None:
    rendered = render_dashboard(_states(), BRANCHES, width=58)
    worker_lines = [line for line in rendered.splitlines()
                    if line.startswith(("A ", "B ", "C ", "  "))]
    assert len(worker_lines) == 6
    assert all(display_width(line) <= 58 for line in rendered.splitlines())
```

- [ ] **Step 6: Run dashboard tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: dashboard tests fail because `render_dashboard` is not defined.

- [ ] **Step 7: Implement the three dashboard width tiers**

Implement explicit `width >= 105`, `70 <= width < 105`, and `width < 70` layouts. Normalize status through a fixed label mapping, reduce tests to passed/failed/warnings/time matches, and synthesize the missing-worker state before rendering.

```python
STATUS_LABELS = {
    "running": "▶ 运行",
    "testing": "▶ 测试",
    "completed_pending_review": "✓ 待审核",
    "failed": "✕ 失败",
    "blocked": "! 阻塞",
    "not_started": "· 未启动",
}


def render_dashboard(..., width: int, refreshed_at: str | None = None) -> str:
    safe_width = max(width, 32)
    if safe_width >= 105:
        return _render_wide_dashboard(...)
    if safe_width >= 70:
        return _render_medium_dashboard(...)
    return _render_narrow_dashboard(...)
```

- [ ] **Step 8: Run dashboard tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: all presentation tests pass.

- [ ] **Step 9: Commit Task 1**

```powershell
git add -- src/codex_supervisor/presentation.py tests/test_codex_supervisor_presentation.py
git commit -m "feat: render compact supervisor dashboard"
```

---

### Task 2: Human-Readable Worker Conversation and Command Events

**Files:**
- Modify: `src/codex_supervisor/presentation.py`
- Modify: `tests/test_codex_supervisor_presentation.py`

**Interfaces:**
- Consumes: `display_width()` and `truncate_display()` from Task 1.
- Produces: `render_worker_header(worker: str, state: Mapping[str, Any], branch: str, width: int) -> str`
- Produces: `render_task(label: str, content: str, width: int) -> str`
- Produces: `render_event(raw_line: str, width: int) -> str`
- Produces privately: `_render_agent_message()`, `_summarize_command()`, `_failure_tail()`, and display-width-aware wrapping helpers.

- [ ] **Step 1: Write failing worker-message tests**

Name the breaks: raw nested JSON remains escaped and unreadable; ordinary C replies are lost; lines exceed terminal width.

```python
def test_structured_agent_message_renders_conversation_fields() -> None:
    raw = json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": json.dumps({
            "status": "blocked",
            "summary": "分类身份不匹配",
            "tests_run": ["单次诊断执行"],
            "blockers": ["C8b taxonomy identity mismatch"],
            "next_action": "停止并等待审核",
        }, ensure_ascii=False)},
    }, ensure_ascii=False)
    rendered = render_event(raw, width=72)
    assert "[C] ✕ 阻塞" in rendered
    assert "分类身份不匹配" in rendered
    assert "阻塞：C8b taxonomy identity mismatch" in rendered
    assert "下一步：停止并等待审核" in rendered
    assert '\\"status\\"' not in rendered
    assert all(display_width(line) <= 72 for line in rendered.splitlines())


def test_plain_agent_message_is_preserved_and_wrapped() -> None:
    raw = json.dumps({"type": "item.completed", "item": {
        "type": "agent_message", "text": "正在检查索引状态，不会执行写入。"}},
        ensure_ascii=False)
    rendered = render_event(raw, width=24)
    assert rendered.startswith("[C]")
    assert "正在检查索引状态" in rendered.replace("\n", "")
    assert all(display_width(line) <= 24 for line in rendered.splitlines())
```

- [ ] **Step 2: Run message tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: import fails for the new worker-rendering functions.

- [ ] **Step 3: Implement worker header, task, and agent-message rendering**

Parse the outer event first, then attempt `json.loads()` only when `item.text` is a string. Treat a decoded mapping with `summary`/`status` as structured; otherwise render the original text. Wrap each labeled field without breaking CJK display width.

```python
def render_event(raw_line: str, width: int) -> str:
    try:
        event = json.loads(raw_line)
    except (json.JSONDecodeError, TypeError):
        return truncate_display("⚠ 无法解析事件", width)
    item = event.get("item") if isinstance(event, dict) else None
    if isinstance(item, dict) and item.get("type") == "agent_message":
        return _render_agent_message(str(item.get("text") or ""), width)
    return _render_non_message_event(event, width)
```

- [ ] **Step 4: Run message tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: message tests pass.

- [ ] **Step 5: Write failing command and fallback tests**

Name the breaks: PowerShell launcher noise dominates commands; successful output floods the window; failures omit the actionable last line; malformed/unknown events crash the observer.

```python
def test_command_events_hide_launcher_and_success_output() -> None:
    started = json.dumps({"type": "item.started", "item": {
        "type": "command_execution",
        "command": '"C:\\\\Windows\\\\powershell.exe" -Command "pytest -q"',
        "status": "in_progress"}})
    completed = json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "command": "pytest -q",
        "aggregated_output": "146 passed in 3.88s", "exit_code": 0,
        "status": "completed"}})
    assert render_event(started, 80) == "▶ 命令\npytest -q"
    assert render_event(completed, 80) == "✓ 退出码 0"


def test_failed_command_shows_only_last_meaningful_line() -> None:
    raw = json.dumps({"type": "item.completed", "item": {
        "type": "command_execution", "command": "python diagnostic.py",
        "aggregated_output": "Traceback...\nValueError: identity mismatch\n",
        "exit_code": 1, "status": "failed"}})
    assert render_event(raw, 80) == (
        "✕ 退出码 1\nValueError: identity mismatch"
    )


def test_malformed_and_unknown_events_degrade_without_raw_json() -> None:
    assert render_event('{"type":', 40) == "⚠ 无法解析事件"
    unknown = render_event(json.dumps({"type": "future.event", "blob": "x" * 200}), 40)
    assert unknown == "· future.event"
```

- [ ] **Step 6: Run command tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: command/fallback assertions fail against the message-only implementation.

- [ ] **Step 7: Implement concise command, lifecycle, error, and fallback rendering**

Strip only a recognized leading PowerShell executable plus `-Command`; remove one matching pair of outer quotes from its payload. For a failed completion, select the last non-empty output line. Render thread/turn start/completion/error as one bounded line and unknown types as `· <type>`.

- [ ] **Step 8: Run all presentation tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_presentation.py -v`

Expected: all tests pass with no warnings.

- [ ] **Step 9: Commit Task 2**

```powershell
git add -- src/codex_supervisor/presentation.py tests/test_codex_supervisor_presentation.py
git commit -m "feat: format worker conversation events"
```

---

### Task 3: Complete-Line Read-Only JSONL Follower

**Files:**
- Create: `src/codex_supervisor/jsonl_tail.py`
- Create: `tests/test_codex_supervisor_jsonl_tail.py`

**Interfaces:**
- Produces: `JsonlFollower(path: Path)` with `read_tail(count: int) -> list[str]` and `read_new() -> list[str]`.
- Guarantees: returns only newline-terminated UTF-8 records; retains an incomplete suffix in memory; resets safely when the file shrinks or its identity changes; never opens the path for writing.

- [ ] **Step 1: Write failing follower tests**

Name the breaks: partial JSON is rendered prematurely; appended multibyte data is corrupted; truncation leaves the follower stuck beyond EOF.

```python
def test_follower_waits_for_complete_utf8_line(tmp_path: Path) -> None:
    path = tmp_path / "C.events.jsonl"
    path.write_bytes('{"text":"中'.encode("utf-8"))
    follower = JsonlFollower(path)
    assert follower.read_tail(50) == []
    with path.open("ab") as handle:
        handle.write('文"}\n'.encode("utf-8"))
    assert follower.read_new() == ['{"text":"中文"}']


def test_follower_returns_last_complete_records(tmp_path: Path) -> None:
    path = tmp_path / "C.events.jsonl"
    path.write_text("one\ntwo\nthree\npartial", encoding="utf-8")
    follower = JsonlFollower(path)
    assert follower.read_tail(2) == ["two", "three"]


def test_follower_restarts_after_truncation(tmp_path: Path) -> None:
    path = tmp_path / "C.events.jsonl"
    path.write_text("old\n", encoding="utf-8")
    follower = JsonlFollower(path)
    assert follower.read_tail(5) == ["old"]
    path.write_text("new\n", encoding="utf-8")
    assert follower.read_new() == ["new"]
```

- [ ] **Step 2: Run follower tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_jsonl_tail.py -v`

Expected: collection fails because `JsonlFollower` does not exist.

- [ ] **Step 3: Implement the minimal binary follower**

Track byte `offset`, `pending`, and file identity. Split only at the last `b"\n"`; decode complete records with UTF-8 and replacement only for irrecoverably invalid bytes. `read_tail()` sets the cursor to current EOF after retaining an incomplete suffix. `read_new()` resets before reading when size decreases or identity changes.

```python
@dataclass
class JsonlFollower:
    path: Path
    _offset: int = 0
    _pending: bytes = b""
    _identity: tuple[int, int] | None = None
    _mtime_ns: int | None = None

    def read_new(self) -> list[str]:
        if not self.path.is_file():
            return []
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        replaced = self._identity not in (None, identity)
        rewritten_at_eof = (
            self._mtime_ns is not None
            and stat.st_mtime_ns != self._mtime_ns
            and stat.st_size <= self._offset
        )
        if replaced or stat.st_size < self._offset or rewritten_at_eof:
            self._offset = 0
            self._pending = b""
        with self.path.open("rb") as handle:
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()
        self._identity = identity
        self._mtime_ns = stat.st_mtime_ns
        return self._consume(chunk)
```

- [ ] **Step 4: Run follower tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_jsonl_tail.py -v`

Expected: all follower tests pass.

- [ ] **Step 5: Add missing-file and append-only read-safety tests**

Name the breaks: a not-started worker raises instead of waiting; an accidental writable open changes the event file.

```python
def test_missing_file_returns_no_records_until_created(tmp_path: Path) -> None:
    path = tmp_path / "C.events.jsonl"
    follower = JsonlFollower(path)
    assert follower.read_tail(50) == []
    path.write_text("created\n", encoding="utf-8")
    assert follower.read_new() == ["created"]


def test_reads_do_not_change_file_bytes_or_mtime(tmp_path: Path) -> None:
    path = tmp_path / "C.events.jsonl"
    path.write_bytes(b"one\ntwo\n")
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    follower = JsonlFollower(path)
    assert follower.read_tail(1) == ["two"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
```

- [ ] **Step 6: Run follower suite and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_jsonl_tail.py -v`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add -- src/codex_supervisor/jsonl_tail.py tests/test_codex_supervisor_jsonl_tail.py
git commit -m "feat: follow complete supervisor event records"
```

---

### Task 4: Integrate Readable Watch and In-Place Dashboard Refresh

**Files:**
- Modify: `src/codex_supervisor/cli.py`
- Modify: `tests/test_codex_supervisor_cli.py`

**Interfaces:**
- Consumes: `render_dashboard()`, `render_worker_header()`, `render_task()`, `render_event()` from `presentation.py`.
- Consumes: `JsonlFollower` from `jsonl_tail.py`.
- Changes private signature: `_watch_worker(store, worker, *, branch, tail, once) -> None`.
- Produces privately: `_terminal_width() -> int`, `_is_interactive_output() -> bool`, `_load_approved_prompts(store, worker) -> list[tuple[str, str]]`, and `_write_dashboard_frame(frame: str, *, first: bool, interactive: bool) -> None`.

- [ ] **Step 1: Replace the raw-watch integration test with a failing readable-output test**

Name the break: CLI can satisfy the old test while still dumping raw JSON; the new assertion checks user-visible conversation and absence of escape-heavy JSON.

```python
def test_watch_once_prints_readable_state_task_and_event_history(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(WorkerState.initial("C").with_status("running"))
    task = _approved_task(project, "C")
    task.write_text(
        "Spec: docs/spec.md\nPlan: docs/plan.md\nAllowed files:\n- x\n"
        "Subagents: forbidden\n检查投影一致性。\n",
        encoding="utf-8",
    )
    store.append_event("C", json.dumps({"type": "item.completed", "item": {
        "type": "agent_message", "text": "预检通过，开始诊断。"}},
        ensure_ascii=False))
    exit_code, stdout, stderr = invoke_cli(
        ["watch", "--worker", "C", "--tail", "5", "--once"],
        project_root=project,
    )
    assert (exit_code, stderr) == (0, "")
    assert "Observer Only" in stdout
    assert "任务" in stdout and "检查投影一致性" in stdout
    assert "[C]" in stdout and "预检通过" in stdout
    assert '"type": "item.completed"' not in stdout
    assert "\x1b[" not in stdout
```

- [ ] **Step 2: Run the watch integration test and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_cli.py::test_watch_once_prints_readable_state_task_and_event_history -v`

Expected: FAIL because current watch prints the raw state JSON and event line.

- [ ] **Step 3: Integrate the formatter and follower into `_watch_worker`**

Pass the configured branch from `_dispatch`. On the first iteration, print the header, every existing approved task/resume file with a distinct label, and the follower's last `tail` complete records. Later iterations call `read_new()`. Flush each rendered event and preserve `--once` without sleeping.

```python
follower = JsonlFollower(store.event_log_path(worker))
print(render_worker_header(worker, state, branch, _terminal_width()))
for label, content in _load_approved_prompts(store, worker):
    print(render_task(label, content, _terminal_width()))
for line in follower.read_tail(tail):
    print(render_event(line, _terminal_width()), flush=True)
if once:
    return
```

- [ ] **Step 4: Run the watch integration and presentation/follower suites**

Run: `python -m pytest tests/test_codex_supervisor_cli.py::test_watch_once_prints_readable_state_task_and_event_history tests/test_codex_supervisor_presentation.py tests/test_codex_supervisor_jsonl_tail.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Write failing dashboard output-mode tests**

Name the breaks: redirected dashboard output receives ANSI cursor codes; the CLI duplicates rendering logic instead of using bounded frames.

```python
def test_dashboard_once_is_compact_and_has_no_cursor_controls(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    store = AtomicStateStore(project / ".codex-supervisor")
    store.write(replace(
        WorkerState.initial("A").with_status("completed_pending_review"),
        tests_summary="409 passed, 3 warnings in 8.86s",
        usage=UsageTotals(input_tokens=246_000_000,
                          output_tokens=655_468,
                          cached_input_tokens=231_070_976),
    ))
    exit_code, stdout, stderr = invoke_cli(["dashboard"], project_root=project)
    assert (exit_code, stderr) == (0, "")
    assert stdout.count("Codex Supervisor") == 1
    assert "rag-a-routing" in stdout and "246.7M" in stdout
    assert "\x1b[" not in stdout
    assert all(display_width(line) <= 120 for line in stdout.splitlines())


def test_dashboard_frame_reuses_screen_only_for_interactive_watch() -> None:
    output = io.StringIO()
    _write_dashboard_frame("frame two", output=output,
                           interactive=True, first=False)
    assert output.getvalue() == "\x1b[H\x1b[Jframe two\n"
    output = io.StringIO()
    _write_dashboard_frame("frame two", output=output,
                           interactive=False, first=False)
    assert output.getvalue() == "frame two\n"
```

- [ ] **Step 6: Run dashboard output-mode tests and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_cli.py -k dashboard -v`

Expected: FAIL because the current dashboard has no compact heading and appends frames.

- [ ] **Step 7: Integrate width-aware frames and TTY-aware refresh**

Build a state mapping for all three workers, synthesize `not_started` when absent, get width from `shutil.get_terminal_size(fallback=(120, 24)).columns`, and pass the current local `HH:MM:SS` string to `render_dashboard`. Use cursor-home plus erase-to-end only when `watch` and stdout is a TTY; otherwise print an ordinary frame.

- [ ] **Step 8: Run all CLI and presentation/follower tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_presentation.py tests/test_codex_supervisor_jsonl_tail.py -v`

Expected: all tests pass with no warnings.

- [ ] **Step 9: Commit Task 4**

```powershell
git add -- src/codex_supervisor/cli.py tests/test_codex_supervisor_cli.py
git commit -m "feat: present readable supervisor observers"
```

---

### Task 5: PowerShell Tail Control, Runbook, and End-to-End Verification

**Files:**
- Modify: `scripts/codex-supervisor/Watch-Worker.ps1`
- Modify: `tests/test_codex_supervisor_powershell.py`
- Modify: `docs/codex/cli-supervisor-runbook.md`

**Interfaces:**
- Preserves: `Watch-Worker.ps1 -Worker <A|B|C> [-Once]`.
- Adds: optional `[ValidateRange(0, 1000)][int]$Tail = 50`, forwarded as `--tail $Tail`.
- Documents: observer-only data flow and output behavior; does not add a control operation.

- [ ] **Step 1: Write a failing executable PowerShell argument test**

Name the break: source-grep tests can pass while `-Tail` is not actually forwarded. Use a temporary fake Python executable script selected through `CODEX_SUPERVISOR_PYTHON`; it records argv, allowing the real wrapper to execute without launching Codex.

```python
@pytest.mark.skipif(os.name != "nt", reason="PowerShell wrapper is Windows-only")
def test_watch_wrapper_forwards_validated_tail(tmp_path: Path) -> None:
    capture = tmp_path / "capture.py"
    fake_python = tmp_path / "python.cmd"
    output = tmp_path / "argv.json"
    capture.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    fake_python.write_text(
        f'@echo off\r\n"{sys.executable}" "{capture}" %*\r\n',
        encoding="utf-8",
    )
    env = os.environ | {"CODEX_SUPERVISOR_PYTHON": str(fake_python)}
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(SCRIPT_ROOT / "Watch-Worker.ps1"),
         "-Worker", "C", "-Tail", "12", "-Once"],
        cwd=Path.cwd(), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0
    argv = json.loads(output.read_text(encoding="utf-8"))
    assert argv[-6:] == ["watch", "--worker", "C", "--tail", "12", "--once"]
```

- [ ] **Step 2: Run the PowerShell test and verify RED**

Run: `python -m pytest tests/test_codex_supervisor_powershell.py::test_watch_wrapper_forwards_validated_tail -v`

Expected: FAIL because `Watch-Worker.ps1` does not accept `-Tail`.

- [ ] **Step 3: Add and forward the optional PowerShell tail parameter**

```powershell
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Worker,
    [ValidateRange(0, 1000)]
    [int]$Tail = 50,
    [switch]$Once
)

$Arguments = @(
    $Supervisor, "watch", "--worker", $Worker, "--tail", $Tail
)
```

Keep the existing `Observer Only` title and close-window safety text unchanged.

- [ ] **Step 4: Run PowerShell tests and verify GREEN**

Run: `python -m pytest tests/test_codex_supervisor_powershell.py -v`

Expected: all PowerShell contract and execution tests pass.

- [ ] **Step 5: Update the runbook**

Document that Dashboard refreshes one frame in place, width tiers hide only secondary data, worker monitors render approved tasks/agent replies/concise command activity, failed commands show the final error line, raw events remain on disk, and observation never writes to sessions or controls processes. Add a `-Tail 100` example without rewriting unrelated runbook content.

- [ ] **Step 6: Run focused and full automated verification**

Run focused supervisor tests:

```powershell
python -m pytest tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_presentation.py tests/test_codex_supervisor_jsonl_tail.py tests/test_codex_supervisor_powershell.py -v
```

Run the full supervisor regression set:

```powershell
python -m pytest tests/test_codex_supervisor_contracts.py tests/test_codex_supervisor_events.py tests/test_codex_supervisor_processes.py tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_powershell.py tests/test_codex_supervisor_presentation.py tests/test_codex_supervisor_jsonl_tail.py -v
```

Expected: zero failures and no unexpected warnings.

- [ ] **Step 7: Perform read-only real-data smoke checks**

Use the configured supervisor Python without starting, resuming, stopping, accepting, or messaging a worker:

```powershell
$env:CODEX_SUPERVISOR_PYTHON = (& powershell.exe -NoProfile -Command ". 'scripts/codex-supervisor/Resolve-SupervisorPython.ps1'; Resolve-SupervisorPython")
& $env:CODEX_SUPERVISOR_PYTHON scripts/codex_supervisor.py dashboard
& $env:CODEX_SUPERVISOR_PYTHON scripts/codex_supervisor.py watch --worker C --tail 12 --once
```

Confirm manually that the dashboard contains one bounded frame, the C output contains `[C]` conversation entries and concise command results, no raw nested event JSON is present, and both commands exit without changing the bytes or modification times of C's state, session, task, and event files.

- [ ] **Step 8: Review diff and commit Task 5**

```powershell
git diff --check
git diff -- scripts/codex-supervisor/Watch-Worker.ps1 tests/test_codex_supervisor_powershell.py docs/codex/cli-supervisor-runbook.md
git add -- scripts/codex-supervisor/Watch-Worker.ps1 tests/test_codex_supervisor_powershell.py docs/codex/cli-supervisor-runbook.md
git commit -m "docs: explain readable supervisor monitors"
```

- [ ] **Step 9: Final verification after all commits**

Run:

```powershell
python -m pytest tests/test_codex_supervisor_contracts.py tests/test_codex_supervisor_events.py tests/test_codex_supervisor_processes.py tests/test_codex_supervisor_cli.py tests/test_codex_supervisor_powershell.py tests/test_codex_supervisor_presentation.py tests/test_codex_supervisor_jsonl_tail.py -q
git status --short
```

Expected: all tests pass. `git status --short` may still show the user's pre-existing unrelated changes, but none of the implementation files from this plan remain uncommitted.
