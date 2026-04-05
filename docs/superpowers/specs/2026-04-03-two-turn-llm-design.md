# Spec: Two-Turn LLM Call via /api/chat

**Date:** 2026-04-03

## Goal

Replace the current single-turn `/api/generate` call with a two-turn `/api/chat` conversation. The first turn feeds the raw article to the LLM with no system prompt or instruction framing. The second turn asks for a concise Chinese title using a specific instruction prompt.

## Motivation

Testing with gemma4 showed better title quality when the model reads the article in isolation first, then is asked for a summary — rather than receiving the article and instruction together.

## Scope

Changes confined to `rename.py` only. All other logic (preamble stripping, log, rename, deduplication) is unchanged.

## Changes to `rename.py`

### Remove

- `SYSTEM_PROMPT` constant
- `PROMPT_TEMPLATE` constant
- Current `summarize_with_llm()` implementation (single-turn `/api/generate`)

### Add

```python
SUMMARY_PROMPT = (
    '總結劇情重點, 你必須只輸出一句摘要，絕對不要提供多個選擇，'
    '絕對不能輸出任何解釋、說明、標點符號或其他文字。'
    ' 輸出必須是單行純文字，不超過15個漢字。'
)
```

### New `summarize_with_llm()` implementation

**Turn 1** — feed article, no instruction:

```
POST /api/chat
{
  "model": "gemma4",
  "messages": [{"role": "user", "content": <article_content>}],
  "stream": false,
  "keep_alive": 0,
  "options": {"temperature": 0.1, "num_predict": 200}
}
```

- Extract `response_text` from `message.content` in the JSON reply.
- If Turn 1 raises an exception or returns an empty `content` → return `None`, do not proceed.

**Turn 2** — ask for title, with full conversation history:

```
POST /api/chat
{
  "model": "gemma4",
  "messages": [
    {"role": "user",      "content": <article_content>},
    {"role": "assistant", "content": <turn1_reply>},
    {"role": "user",      "content": SUMMARY_PROMPT}
  ],
  "stream": false,
  "keep_alive": 0,
  "options": {
    "temperature": 0.1,
    "num_predict": 40,
    "stop": ["\n", "。\n", "\n\n", "，这", "，這", " 这", " 這"]
  }
}
```

- Extract title from `message.content`.
- Pass through `extract_title()` → `clean_filename()` → `truncate_to_30_cjk()` → `is_valid_title()`.
- If any step fails or result is invalid → return `None`.

## Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Turn 1 HTTP exception | Return `None` |
| Turn 1 empty `content` | Return `None`, skip Turn 2 |
| Turn 2 HTTP exception | Return `None` |
| Turn 2 empty or invalid title | Return `None` |

## Response JSON shape (`/api/chat`)

```json
{
  "message": {
    "role": "assistant",
    "content": "..."
  }
}
```

Access via `r.json()["message"]["content"]` (vs current `r.json()["response"]`).

## Testing

- Existing tests that mock `requests.post` must be updated to:
  - Return `{"message": {"role": "assistant", "content": "..."}}` instead of `{"response": "..."}`
  - Expect two `requests.post` calls per `summarize_with_llm()` invocation
- New test: Turn 1 empty response → returns `None` without making Turn 2 call
- New test: Turn 1 exception → returns `None` without making Turn 2 call
- `test_summarize_default_model_is_gemma4` updated to verify model in chat payload

## Out of Scope

- Changes to `strip_preamble`, `find_unique_stem`, `main`, log, or rename logic
- Retry logic
- Streaming mode
