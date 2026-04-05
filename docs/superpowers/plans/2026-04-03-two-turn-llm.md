# Two-Turn LLM Call Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-turn `/api/generate` call with a two-turn `/api/chat` conversation — Turn 1 feeds the raw article, Turn 2 asks for the Chinese title summary.

**Architecture:** `summarize_with_llm()` in `rename.py` is rewritten to POST to `/api/chat` twice. Turn 1 sends the article with no instruction; its reply is forwarded as assistant context in Turn 2, which asks for the title via `SUMMARY_PROMPT`. All other logic is untouched.

**Tech Stack:** Python 3.13, requests, pytest, unittest.mock

---

### Task 1: Rewrite tests for two-turn `/api/chat`

**Files:**
- Modify: `tests/test_rename.py` (lines 262–364)

The current tests mock `requests.post` returning `{'response': '...'}` (the `/api/generate` shape). After this task the tests will expect the `/api/chat` shape (`{'message': {'role': 'assistant', 'content': '...'}}`) and two `post` calls per `summarize_with_llm()` invocation.

**TDD discipline:** complete all steps in this task before touching `rename.py`. The tests must fail at Step 2, then pass at the end of Task 2.

- [ ] **Step 1: Add a helper at the top of the test block (around line 247)**

In `tests/test_rename.py`, just after the `from unittest.mock import patch` import line, add:

```python
from unittest.mock import MagicMock

def _chat(content):
    """Return a mock requests.Response whose .json() yields a /api/chat reply."""
    m = MagicMock()
    m.json.return_value = {'message': {'role': 'assistant', 'content': content}}
    return m
```

- [ ] **Step 2: Replace `test_summarize_returns_clean_title`**

Replace the entire function (currently lines 262–268) with:

```python
def test_summarize_returns_clean_title():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('  主角逆襲成功贏回尊嚴  '),
        ]
        result = summarize_with_llm('some content', 'gemma4')
        assert result == '主角逆襲成功贏回尊嚴'
```

- [ ] **Step 3: Replace `test_summarize_strips_illegal_chars`**

Replace (currently lines 271–277) with:

```python
def test_summarize_strips_illegal_chars():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('標題/有:非法*字元'),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert '/' not in result
        assert ':' not in result
        assert '*' not in result
```

- [ ] **Step 4: Replace `test_summarize_truncates_at_30_cjk`**

Replace (currently lines 280–284) with:

```python
def test_summarize_truncates_at_30_cjk():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('一' * 40),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert result == '一' * 30
```

- [ ] **Step 5: Replace `test_summarize_returns_none_on_empty_response`**

Replace (currently lines 287–291) with:

```python
def test_summarize_returns_none_on_empty_response():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('   '),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert result is None
```

- [ ] **Step 6: Replace `test_summarize_returns_none_on_request_error`**

Replace (currently lines 294–297) with:

```python
def test_summarize_returns_none_on_request_error():
    with patch('rename.requests.post', side_effect=Exception('timeout')):
        result = summarize_with_llm('content', 'gemma4')
        assert result is None
```

- [ ] **Step 7: Replace `test_summarize_sends_correct_prompt`**

The old test checked `call_kwargs['prompt']` and `'system' in call_kwargs` — those keys don't exist in `/api/chat`. Replace (currently lines 300–308) with:

```python
def test_summarize_two_turn_message_structure():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('初步回應'),
            _chat('標題'),
        ]
        summarize_with_llm('文章內容', 'gemma4')

        assert mock_post.call_count == 2

        # Turn 1: single user message containing the article, no system prompt
        turn1_payload = mock_post.call_args_list[0][1]['json']
        assert turn1_payload['model'] == 'gemma4'
        assert turn1_payload['messages'] == [{'role': 'user', 'content': '文章內容'}]
        assert 'system' not in turn1_payload

        # Turn 2: article + assistant reply + SUMMARY_PROMPT
        from rename import SUMMARY_PROMPT
        turn2_payload = mock_post.call_args_list[1][1]['json']
        assert turn2_payload['model'] == 'gemma4'
        assert turn2_payload['messages'][0] == {'role': 'user', 'content': '文章內容'}
        assert turn2_payload['messages'][1] == {'role': 'assistant', 'content': '初步回應'}
        assert turn2_payload['messages'][2] == {'role': 'user', 'content': SUMMARY_PROMPT}
```

- [ ] **Step 8: Replace `test_summarize_default_model_is_gemma4`**

Replace (currently lines 311–316) with:

```python
def test_summarize_default_model_is_gemma4():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('回應'), _chat('標題')]
        summarize_with_llm('content')  # no model argument
        assert mock_post.call_args_list[0][1]['json']['model'] == 'gemma4'
        assert mock_post.call_args_list[1][1]['json']['model'] == 'gemma4'
```

- [ ] **Step 9: Replace `test_summarize_uses_keep_alive_zero`**

Replace (currently lines 358–363) with:

```python
def test_summarize_uses_keep_alive_zero():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('回應'), _chat('標題')]
        summarize_with_llm('content', 'gemma4')
        assert mock_post.call_args_list[0][1]['json']['keep_alive'] == 0
        assert mock_post.call_args_list[1][1]['json']['keep_alive'] == 0
```

- [ ] **Step 10: Add three new tests after `test_summarize_uses_keep_alive_zero`**

```python
def test_summarize_turn1_empty_returns_none_without_turn2():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('')]
        result = summarize_with_llm('content', 'gemma4')
        assert result is None
        assert mock_post.call_count == 1  # Turn 2 never called


def test_summarize_turn1_exception_returns_none():
    with patch('rename.requests.post', side_effect=Exception('network error')):
        result = summarize_with_llm('content', 'gemma4')
        assert result is None


def test_summarize_turn2_exception_returns_none():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('回應'), Exception('timeout')]
        result = summarize_with_llm('content', 'gemma4')
        assert result is None
```

- [ ] **Step 11: Run tests — expect failures**

```
python -m pytest tests/test_rename.py -v -k "summarize" 2>&1
```

Expected: several failures (implementation still uses old `/api/generate` path). This confirms the tests are testing the right thing.

- [ ] **Step 12: Commit failing tests**

```bash
git add tests/test_rename.py
git commit -m "test: rewrite summarize tests for two-turn /api/chat"
```

---

### Task 2: Rewrite `summarize_with_llm` in `rename.py`

**Files:**
- Modify: `rename.py` (lines 143–228)

- [ ] **Step 1: Remove `SYSTEM_PROMPT`, `PROMPT_TEMPLATE`, and `_TITLE_PREFIX_RE` — wait**

`_TITLE_PREFIX_RE`, `_GUILLEMETS_RE`, `_CHAPTER_RE` are used by `extract_title()` which stays. Only remove the prompt constants.

Remove lines 143–154 (the two constants):

```python
# DELETE these two blocks:
SYSTEM_PROMPT = (
    '你是一個專業的文章命名助手。'
    ...
)
PROMPT_TEMPLATE = (
    '請為以下文章生成一個不超過15個漢字的中文標題。'
    ...
)
```

- [ ] **Step 2: Add `SUMMARY_PROMPT` in their place**

At the same location (after `OLLAMA_URL = 'http://localhost:11434'`), add:

```python
SUMMARY_PROMPT = (
    '總結劇情重點, 你必須只輸出一句摘要，絕對不要提供多個選擇，'
    '絕對不能輸出任何解釋、說明、標點符號或其他文字。'
    ' 輸出必須是單行純文字，不超過15個漢字。'
)
```

- [ ] **Step 3: Replace `summarize_with_llm()` body**

Replace the entire `summarize_with_llm()` function (find it by its `def` line) with:

```python
def summarize_with_llm(content: str, model: str = 'gemma4'):
    try:
        r1 = requests.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': content}],
                'stream': False,
                'keep_alive': 0,
                'options': {'temperature': 0.1, 'num_predict': 200},
            },
            timeout=120,
        )
        turn1_reply = r1.json().get('message', {}).get('content', '').strip()
    except Exception:
        return None

    if not turn1_reply:
        return None

    try:
        r2 = requests.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': model,
                'messages': [
                    {'role': 'user', 'content': content},
                    {'role': 'assistant', 'content': turn1_reply},
                    {'role': 'user', 'content': SUMMARY_PROMPT},
                ],
                'stream': False,
                'keep_alive': 0,
                'options': {
                    'temperature': 0.1,
                    'num_predict': 40,
                    'stop': ['\n', '。\n', '\n\n', '，这', '，這', ' 这', ' 這'],
                },
            },
            timeout=120,
        )
        raw = r2.json().get('message', {}).get('content', '').strip()
    except Exception:
        return None

    print(f'  [LLM raw] {raw!r}', file=sys.stderr)

    if not raw:
        return None

    title = extract_title(raw)
    title = clean_filename(title)
    title = truncate_to_30_cjk(title)
    return title if is_valid_title(title) else None
```

- [ ] **Step 4: Run all tests — expect all pass**

```
python -m pytest -v 2>&1
```

Expected: 63 passed (60 existing + 3 new from Task 1 Step 10), 0 failed.

- [ ] **Step 5: Commit**

```bash
git add rename.py
git commit -m "feat: switch to two-turn /api/chat for LLM title generation"
```
