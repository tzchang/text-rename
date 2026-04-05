# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Read a directory provided by the user, list all `.txt` files, read their contents, use a local LLM (via Ollama) to generate a concise Chinese title (≤15 CJK characters), and rename each file accordingly. Already-renamed files are skipped via a JSON log.

## Environment

- Python 3.13 virtual environment at `venv/`
- Activate: `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows)
- Dependencies: `pip install -r requirements.txt` (`requests`, `pytest`)

## Running

```bash
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

python rename.py <folder>
```

Requires Ollama running locally (`ollama serve`) with model `gemma4` available.

## Testing

```bash
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

pytest
```

Tests live in `tests/`. Run a single test file: `pytest tests/test_rename.py -v`.

## Key Architecture

- **`rename.py`** — single-file script, all logic here
- **`strip_preamble()`** — removes boilerplate from the first 5 paragraphs (split by `\n\n`), but only if the paragraph is ≤ 3000 chars (larger blocks are story content, not headers). Keywords: `廣告 版權 作者： 出版 All Rights Reserved 禁止轉載 付費 訂閱 瑪麗`. Note: `關注`/`點贊`/`轉發` were intentionally removed — they are common in story dialogue. Truncates to 6000 chars. Files with < 100 chars after stripping are skipped (logged as error, no LLM call).
- **`summarize_with_llm()`** — two-turn `/api/chat` with `think: False` (disables Gemma4's thinking mode). Turn 1 sends the article prefixed with `請閱讀以下文章：`; Turn 2 asks for a ≤15-char Chinese title via `SUMMARY_PROMPT`. Uses `num_ctx: 32768` and `keep_alive: 0`. Extracts title via `extract_title()`, cleans and truncates to 30 CJK chars.
- **`wait_for_model_unloaded()`** — polls `GET /api/ps` after each file until the model is confirmed unloaded (or 30s timeout), preventing memory exhaustion across large batches
- **`_CHAPTER_RE`** — rejects titles matching bare chapter headings (`第X章`, `第X回`). `節` was intentionally excluded: `第一節` is ambiguous (could be "school period", not just "chapter section").
- **`find_unique_stem()`** — uses `difflib.SequenceMatcher` (ratio > 0.8) to avoid near-duplicate filenames; appends `_2` … `_20` suffix if needed
- **`.rename_log.json`** — written to the target folder; tracks `old_name`, `new_name`, `status`, `timestamp` per file. Status `done` = skip on next run; `error:…` = retry on next run
- **`discover_files()`** — skips files whose original name OR new name already appears in the log as `done`

## Known Gotchas

- **Gemma4 thinking mode**: Gemma4 is a reasoning model that by default spends tokens on internal thinking (`message.thinking`) and outputs nothing to `message.content`. Always pass `"think": false` in Ollama API calls or Turn 1 will silently return empty responses. Diagnosed via `done_reason='length'` + `output_tokens=500` + `message.content len=0`.
