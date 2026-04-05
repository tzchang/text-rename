# Spec: Wait for Model Memory Release Between Files

**Date:** 2026-04-04

## Problem

When processing a folder of 10+ `.txt` files, the LLM returns valid responses for the first 2 files, then empty responses for all subsequent files. Suspected cause: Ollama does not fully release GPU/RAM between files despite `keep_alive: 0`, causing the model to silently fail on subsequent loads.

## Goal

After each file is processed (success or error), poll Ollama's `GET /api/ps` endpoint until the model is confirmed unloaded before proceeding to the next file.

## Scope

Changes confined to `rename.py` only. No new files. No changes to LLM call logic, log format, or CLI interface.

## Changes to `rename.py`

### New function: `wait_for_model_unloaded(model, timeout=30)`

Add near `check_ollama()`:

```python
def wait_for_model_unloaded(model: str, timeout: int = 30) -> bool:
    """Poll GET /api/ps until model is no longer loaded, or timeout expires.
    Returns True if confirmed unloaded, False if timeout reached."""
    import time
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

**Model name matching:** `'gemma4'.split(':')[0]` → `'gemma4'`, checked as prefix against each entry in `/api/ps` (e.g. `'gemma4:latest'`). This handles both `gemma4` and `gemma4:latest` style names.

**Timeout:** 30 seconds default. If timeout is reached, log a warning and continue — do not abort the batch.

**`/api/ps` failure:** Swallowed silently; loop continues until timeout. This prevents a transient network error from blocking the batch.

### Modified `main()` loop

After each file's `save_log()` call (on both success and all error paths), call:

```python
freed = wait_for_model_unloaded(model)
if not freed:
    print(
        f'  Warning: {model} still loaded after 30s, continuing anyway',
        file=sys.stderr,
    )
```

This must be placed at every exit point of the per-file loop body — currently there are 5 `continue` statements plus the success path. The call is inserted before each `continue` and at the end of the loop body.

`model` is `summarize_with_llm`'s default (`'gemma4'`) since `main()` does not accept a model argument.

## Behaviour Table

| Situation | Result |
|-----------|--------|
| Model unloads quickly | Proceed immediately after confirmation |
| Model unloads within 30s | Proceed after confirmation |
| Model still loaded after 30s | Print warning to stderr, proceed anyway |
| `/api/ps` returns error | Retry until timeout, then warn and proceed |
| Last file in batch | Same logic — no special case |

## Testing

- New unit test: mock `requests.get` to return an empty `models` list → `wait_for_model_unloaded` returns `True` immediately
- New unit test: mock `requests.get` to always return the model as loaded → `wait_for_model_unloaded` returns `False` after timeout (use short timeout in test)
- New unit test: mock `requests.get` to raise an exception → `wait_for_model_unloaded` returns `False` after timeout
- Integration test for `main()`: verify `wait_for_model_unloaded` is called once per file processed

## Out of Scope

- Changing `keep_alive` values
- Exposing `timeout` as a CLI argument
- Retry logic on LLM failures
- Changes to `summarize_with_llm()`
