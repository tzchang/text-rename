# Memory Release Check Between Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each `.txt` file is processed, poll Ollama's `GET /api/ps` until the model is confirmed unloaded before proceeding to the next file.

**Architecture:** Add `wait_for_model_unloaded(model, timeout)` to `rename.py` near `check_ollama()`. Update every exit point (5 `continue` + 1 success) in `main()`'s per-file loop to call it after `save_log()`. If timeout expires, print a warning to stderr and continue.

**Tech Stack:** Python 3.13, requests, pytest, unittest.mock

---

### Task 1: Write failing tests for `wait_for_model_unloaded`

**Files:**
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Add import for `wait_for_model_unloaded` in the check_ollama import block**

Find the line:
```python
from rename import check_ollama, summarize_with_llm
```
Change it to:
```python
from rename import check_ollama, summarize_with_llm, wait_for_model_unloaded
```

- [ ] **Step 2: Add 5 unit tests for `wait_for_model_unloaded` after `test_check_ollama_failure`**

Insert these tests after `test_check_ollama_failure`:

```python
def test_wait_returns_true_when_no_models_loaded():
    with patch('rename.requests.get') as mock_get:
        mock_get.return_value.json.return_value = {'models': []}
        result = wait_for_model_unloaded('gemma4', timeout=5)
        assert result is True
        assert mock_get.call_count == 1


def test_wait_returns_true_when_different_model_loaded():
    with patch('rename.requests.get') as mock_get:
        mock_get.return_value.json.return_value = {
            'models': [{'name': 'llama3:latest'}]
        }
        result = wait_for_model_unloaded('gemma4', timeout=5)
        assert result is True


def test_wait_returns_false_on_timeout():
    # timeout=0: deadline already expired when loop first checks
    with patch('rename.requests.get') as mock_get:
        mock_get.return_value.json.return_value = {
            'models': [{'name': 'gemma4:latest'}]
        }
        result = wait_for_model_unloaded('gemma4', timeout=0)
        assert result is False


def test_wait_retries_until_model_unloads():
    with patch('rename.requests.get') as mock_get, \
         patch('rename.time.sleep'):
        mock_get.side_effect = [
            MagicMock(**{'json.return_value': {'models': [{'name': 'gemma4:latest'}]}}),
            MagicMock(**{'json.return_value': {'models': []}}),
        ]
        result = wait_for_model_unloaded('gemma4', timeout=10)
        assert result is True
        assert mock_get.call_count == 2


def test_wait_returns_false_on_request_exception():
    with patch('rename.requests.get', side_effect=Exception('connection refused')):
        result = wait_for_model_unloaded('gemma4', timeout=0)
        assert result is False
```

- [ ] **Step 3: Add integration test for `main()` calling wait per file**

In the main integration test block (near `test_main_renames_file`), add this new test:

```python
def test_main_calls_wait_for_memory_after_each_file(tmp_path):
    (tmp_path / 'a.txt').write_text('content a', encoding='utf-8')
    (tmp_path / 'b.txt').write_text('content b', encoding='utf-8')

    with patch('rename.check_ollama', return_value=True), \
         patch('rename.summarize_with_llm', return_value='標題'), \
         patch('rename.wait_for_model_unloaded', return_value=True) as mock_wait, \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    assert mock_wait.call_count == 2
```

- [ ] **Step 4: Run tests — expect failures**

```
python -m pytest tests/test_rename.py -v -k "wait or memory" 2>&1
```

Expected: all new tests FAIL (ImportError on `wait_for_model_unloaded`). Confirms TDD setup is correct.

- [ ] **Step 5: Commit failing tests**

```bash
git add tests/test_rename.py
git commit -m "test: add tests for wait_for_model_unloaded"
```

---

### Task 2: Implement `wait_for_model_unloaded` and update `main()`

**Files:**
- Modify: `rename.py`

- [ ] **Step 1: Add `import time` to the top-level imports**

Find the imports block at the top of `rename.py`:
```python
import argparse
import difflib
import json
import os
import re
import sys
import requests
from datetime import datetime, timezone
```
Change to:
```python
import argparse
import difflib
import json
import os
import re
import sys
import time
import requests
from datetime import datetime, timezone
```

- [ ] **Step 2: Add `wait_for_model_unloaded` after `check_ollama()`**

Find the line after `check_ollama()` ends:
```python
def check_ollama() -> bool:
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        return r.status_code == 200
    except Exception:
        return False
```

Add the new function immediately after it:

```python
def wait_for_model_unloaded(model: str, timeout: int = 30) -> bool:
    """Poll GET /api/ps until model is no longer loaded, or timeout expires.
    Returns True if confirmed unloaded, False if timeout reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f'{OLLAMA_URL}/api/ps', timeout=5)
            loaded = [m['name'] for m in r.json().get('models', [])]
            if not any(m.startswith(model.split(':')[0]) for m in loaded):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False
```

- [ ] **Step 3: Run unit tests for `wait_for_model_unloaded` — expect pass**

```
python -m pytest tests/test_rename.py -v -k "wait" 2>&1
```

Expected: 5 unit tests PASS. Integration test `test_main_calls_wait_for_memory_after_each_file` still FAILS (main() not updated yet).

- [ ] **Step 4: Update `main()` — add wait after every `save_log()` call**

There are 6 places in the `for filename in files:` loop where `save_log(log_path, log)` is called. Add the wait+warning block after each one.

**Exit 1 — read error** (around line 284–287). Replace:
```python
            log[filename] = make_log_entry(filename, None, f'error: {e}')
            save_log(log_path, log)
            continue
```
with:
```python
            log[filename] = make_log_entry(filename, None, f'error: {e}')
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue
```

**Exit 2 — LLM empty response** (around line 293–296). Replace:
```python
            log[filename] = make_log_entry(filename, None, 'error: LLM returned empty response')
            save_log(log_path, log)
            continue
```
with:
```python
            log[filename] = make_log_entry(filename, None, 'error: LLM returned empty response')
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue
```

**Exit 3 — no unique stem** (around line 301–305). Replace:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue
```
with:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue
```

**Exit 4 — target path exists** (around line 311–315). Replace:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue
```
with:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue
```

**Exit 5 — rename failed** (around line 320–324). Replace:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue
```
with:
```python
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue
```

**Exit 6 — success** (around line 326–328). Replace:
```python
        log[filename] = make_log_entry(filename, new_filename, 'done')
        save_log(log_path, log)
        print(f'  Renamed to: {new_filename}')
```
with:
```python
        log[filename] = make_log_entry(filename, new_filename, 'done')
        save_log(log_path, log)
        print(f'  Renamed to: {new_filename}')
        if not wait_for_model_unloaded('gemma4'):
            print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                  file=sys.stderr)
```

- [ ] **Step 5: Run all tests — expect 69 pass**

```
python -m pytest -v 2>&1
```

Expected: 69 passed (63 existing + 5 unit + 1 integration), 0 failed.

- [ ] **Step 6: Commit**

```bash
git add rename.py
git commit -m "feat: wait for model memory release between files"
```
