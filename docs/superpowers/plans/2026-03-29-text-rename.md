# Text Rename Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single Python CLI script that renames `.txt` files using a local Ollama LLM to generate ≤30 Chinese character filenames, with a per-folder log to skip already-processed files.

**Architecture:** Single script `rename.py` with pure helper functions tested in isolation, plus a `main()` orchestration loop. Tests use pytest with temporary directories and a mock Ollama HTTP response — no live LLM required during tests.

**Tech Stack:** Python 3.14, `requests` (Ollama REST API), `pytest`, `difflib`, standard library only otherwise.

---

## File Map

| File | Purpose |
|---|---|
| `rename.py` | Main script — all logic |
| `tests/test_rename.py` | All unit tests |
| `requirements.txt` | `requests` and `pytest` |

---

### Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_rename.py` (empty scaffold)

- [ ] **Step 1: Create requirements.txt**

```
requests
pytest
```

- [ ] **Step 2: Install dependencies**

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Expected: installs without error.

- [ ] **Step 3: Create .gitignore**

Create `.gitignore`:

```
venv/
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 4: Create test scaffold**

Create `tests/__init__.py` (empty file).

Create `tests/test_rename.py`:

```python
# tests/test_rename.py
```

- [ ] **Step 5: Verify pytest runs**

```bash
source venv/bin/activate
pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt tests/
git commit -m "feat: add project scaffold and test infrastructure"
```

---

### Task 2: CJK utilities

**Files:**
- Modify: `rename.py` (create with these functions)
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rename.py`:

```python
from rename import is_cjk, truncate_to_30_cjk, clean_filename


def test_is_cjk_main_block():
    assert is_cjk('你') is True
    assert is_cjk('A') is False
    assert is_cjk('1') is False


def test_is_cjk_extension_a():
    # U+3400 is first char of Extension A
    assert is_cjk('\u3400') is True


def test_is_cjk_compatibility():
    # U+F900 is first char of Compatibility Ideographs
    assert is_cjk('\uF900') is True


def test_truncate_no_truncation_needed():
    title = '短標題'  # 3 CJK chars
    assert truncate_to_30_cjk(title) == '短標題'


def test_truncate_exactly_30():
    title = '一' * 30
    assert truncate_to_30_cjk(title) == '一' * 30


def test_truncate_at_30th_cjk():
    title = '一' * 31
    assert truncate_to_30_cjk(title) == '一' * 30


def test_truncate_drops_trailing_non_cjk():
    # 30 CJK chars then ASCII — ASCII should be dropped
    title = '一' * 30 + 'abc'
    assert truncate_to_30_cjk(title) == '一' * 30


def test_truncate_non_cjk_between_cjk():
    # Non-CJK chars between CJK chars are preserved up to 30th CJK
    title = '一A二B三'  # 3 CJK, interleaved ASCII
    assert truncate_to_30_cjk(title) == '一A二B三'


def test_clean_filename_removes_illegal_chars():
    assert clean_filename('a/b\\c:d*e?f"g<h>i|j') == 'abcdefghij'


def test_clean_filename_strips_whitespace():
    assert clean_filename('  hello world  ') == 'hello world'


def test_clean_filename_empty_after_strip():
    assert clean_filename('///') == ''
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source venv/bin/activate
pytest tests/test_rename.py -v
```

Expected: `ImportError: cannot import name 'is_cjk' from 'rename'` or `ModuleNotFoundError`.

- [ ] **Step 3: Implement the functions**

Create `rename.py`:

```python
#!/usr/bin/env python3
import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone


def is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF or  # CJK Unified Ideographs
        0x3400 <= cp <= 0x4DBF or  # Extension A
        0xF900 <= cp <= 0xFAFF     # Compatibility Ideographs
    )


def truncate_to_30_cjk(text: str) -> str:
    count = 0
    for i, ch in enumerate(text):
        if is_cjk(ch):
            count += 1
            if count == 30:
                return text[:i + 1]
    return text


def clean_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[/\\:*?"<>|]', '', name)
    return name
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "cjk or clean_filename"
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add CJK utilities and filename cleaner"
```

---

### Task 3: Preamble stripping

**Files:**
- Modify: `rename.py`
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rename.py`:

```python
from rename import strip_preamble


def test_strip_preamble_no_ads():
    content = '正文第一段\n\n正文第二段\n\n正文第三段'
    assert strip_preamble(content) == content


def test_strip_preamble_removes_copyright_paragraph():
    content = '版權所有 禁止轉載\n\n正文第一段\n\n正文第二段'
    result = strip_preamble(content)
    assert '版權' not in result
    assert '正文第一段' in result


def test_strip_preamble_removes_ad_paragraph():
    content = '廣告：點贊關注\n\n正文內容'
    result = strip_preamble(content)
    assert '廣告' not in result
    assert '正文內容' in result


def test_strip_preamble_lz_only_in_first_paragraph():
    content = 'LZ平台首發\n\n正文LZ說了什麼\n\n更多內容'
    result = strip_preamble(content)
    # First para removed (LZ in first para), second para kept (LZ elsewhere allowed)
    assert 'LZ平台首發' not in result
    assert '正文LZ說了什麼' in result


def test_strip_preamble_only_checks_first_5():
    paragraphs = ['廣告段落'] + ['正文{}'.format(i) for i in range(10)]
    content = '\n\n'.join(paragraphs)
    result = strip_preamble(content)
    assert '廣告段落' not in result
    # Content beyond first 5 paragraphs is always kept
    for i in range(5, 10):
        assert '正文{}'.format(i) in result


def test_strip_preamble_truncates_to_6000():
    long_content = '一' * 7000
    result = strip_preamble(long_content)
    assert len(result) == 6000


def test_strip_preamble_no_truncation_under_6000():
    content = '正文' * 100  # 200 chars
    result = strip_preamble(content)
    assert len(result) == 200
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rename.py -v -k "preamble"
```

Expected: `ImportError: cannot import name 'strip_preamble'`.

- [ ] **Step 3: Implement strip_preamble**

Append to `rename.py`:

```python
PREAMBLE_KEYWORDS = [
    '廣告', '版權', '作者：', '出版', 'All Rights Reserved',
    '禁止轉載', '付費', '訂閱', '關注', '點贊', '轉發', '瑪麗',
]


def strip_preamble(content: str) -> str:
    paragraphs = content.split('\n\n')
    result = []
    for i, para in enumerate(paragraphs):
        if i < 5:
            if i == 0 and 'LZ' in para:
                continue
            if any(kw in para for kw in PREAMBLE_KEYWORDS):
                continue
        result.append(para)
    cleaned = '\n\n'.join(result)
    if len(cleaned) > 6000:
        cleaned = cleaned[:6000]
    return cleaned
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "preamble"
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add preamble stripping with keyword filter and truncation"
```

---

### Task 4: Log management

**Files:**
- Modify: `rename.py`
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rename.py`:

```python
import json
import tempfile
from pathlib import Path
from rename import load_log, save_log, make_log_entry


def test_load_log_creates_empty_when_missing(tmp_path):
    log_path = tmp_path / '.rename_log.json'
    log = load_log(str(log_path))
    assert log == {}


def test_load_log_reads_existing(tmp_path):
    log_path = tmp_path / '.rename_log.json'
    data = {'foo.txt': {'old_name': 'foo.txt', 'new_name': 'bar.txt',
                         'status': 'done', 'timestamp': '2026-01-01T00:00:00+00:00'}}
    log_path.write_text(json.dumps(data), encoding='utf-8')
    log = load_log(str(log_path))
    assert log['foo.txt']['new_name'] == 'bar.txt'


def test_load_log_backs_up_corrupted(tmp_path):
    log_path = tmp_path / '.rename_log.json'
    log_path.write_text('not valid json', encoding='utf-8')
    log = load_log(str(log_path))
    assert log == {}
    bak_files = list(tmp_path.glob('.rename_log.json.bak.*'))
    assert len(bak_files) == 1


def test_save_log_writes_json(tmp_path):
    log_path = tmp_path / '.rename_log.json'
    log = {'foo.txt': {'old_name': 'foo.txt', 'new_name': 'bar.txt',
                        'status': 'done', 'timestamp': '2026-01-01T00:00:00+00:00'}}
    save_log(str(log_path), log)
    data = json.loads(log_path.read_text(encoding='utf-8'))
    assert data['foo.txt']['status'] == 'done'


def test_make_log_entry_done():
    entry = make_log_entry('old.txt', 'new.txt', 'done')
    assert entry['old_name'] == 'old.txt'
    assert entry['new_name'] == 'new.txt'
    assert entry['status'] == 'done'
    assert '+00:00' in entry['timestamp']


def test_make_log_entry_error():
    entry = make_log_entry('old.txt', None, 'error: something went wrong')
    assert entry['new_name'] is None
    assert entry['status'].startswith('error:')
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rename.py -v -k "log"
```

Expected: `ImportError: cannot import name 'load_log'`.

- [ ] **Step 3: Implement log functions**

Append to `rename.py`:

```python
def load_log(log_path: str) -> dict:
    if not os.path.exists(log_path):
        return {}
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        bak_path = log_path + f'.bak.{ts}'
        try:
            os.rename(log_path, bak_path)
            print(f'Warning: corrupted log backed up to {bak_path}', file=sys.stderr)
        except OSError:
            pass
        return {}


def save_log(log_path: str, log: dict) -> None:
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def make_log_entry(old_name: str, new_name, status: str) -> dict:
    return {
        'old_name': old_name,
        'new_name': new_name,
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "log"
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add log load/save with corruption backup"
```

---

### Task 5: File discovery and filename safety

**Files:**
- Modify: `rename.py`
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rename.py`:

```python
from rename import discover_files, find_unique_stem, build_taken_stems


def test_discover_files_lists_txt(tmp_path):
    (tmp_path / 'a.txt').write_text('x')
    (tmp_path / 'b.txt').write_text('x')
    (tmp_path / 'c.md').write_text('x')
    files = discover_files(str(tmp_path), {})
    assert set(files) == {'a.txt', 'b.txt'}


def test_discover_files_skips_done(tmp_path):
    (tmp_path / 'a.txt').write_text('x')
    (tmp_path / 'b.txt').write_text('x')
    log = {'a.txt': {'status': 'done', 'new_name': 'renamed.txt'}}
    files = discover_files(str(tmp_path), log)
    assert files == ['b.txt']


def test_discover_files_retries_error(tmp_path):
    (tmp_path / 'a.txt').write_text('x')
    log = {'a.txt': {'status': 'error: something', 'new_name': None}}
    files = discover_files(str(tmp_path), log)
    assert files == ['a.txt']


def test_build_taken_stems_from_disk_and_log(tmp_path):
    (tmp_path / 'existing.txt').write_text('x')
    log = {'old.txt': {'status': 'done', 'new_name': 'renamed.txt'}}
    stems = build_taken_stems(str(tmp_path), log)
    assert 'existing' in stems
    assert 'renamed' in stems


def test_find_unique_stem_no_conflict():
    taken = {'other', 'thing'}
    assert find_unique_stem('新標題', taken) == '新標題'


def test_find_unique_stem_exact_match():
    taken = {'新標題'}
    result = find_unique_stem('新標題', taken)
    assert result == '新標題_2'


def test_find_unique_stem_similar_match():
    # Very similar name should trigger suffix
    taken = {'主角逆襲贏麻了'}
    result = find_unique_stem('主角逆襲贏麻了', taken)
    assert result == '主角逆襲贏麻了_2'


def test_find_unique_stem_returns_none_after_20():
    taken = {'新標題'} | {f'新標題_{i}' for i in range(2, 21)}
    result = find_unique_stem('新標題', taken)
    assert result is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rename.py -v -k "discover or taken or unique_stem"
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the functions**

Append to `rename.py`:

```python
def discover_files(folder: str, log: dict) -> list:
    done_keys = {k for k, v in log.items() if v.get('status') == 'done'}
    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith('.txt') and f not in done_keys
    )
    return files


def build_taken_stems(folder: str, log: dict) -> set:
    disk_stems = {
        os.path.splitext(f)[0]
        for f in os.listdir(folder)
        if f.lower().endswith('.txt')
    }
    log_stems = {
        os.path.splitext(v['new_name'])[0]
        for v in log.values()
        if v.get('status') == 'done' and v.get('new_name')
    }
    return disk_stems | log_stems


def find_unique_stem(proposed_stem: str, taken_stems: set):
    # is_too_similar checks the candidate against all taken entries including exact
    # matches (ratio=1.0). The primary exhaustion path is exact matches: e.g. if
    # taken_stems already contains '新標題', '新標題_2', ..., '新標題_20', the loop
    # will exhaust all slots and return None.
    def is_too_similar(stem):
        for taken in taken_stems:
            ratio = difflib.SequenceMatcher(None, stem, taken).ratio()
            if ratio > 0.8:
                return True
        return False

    if not is_too_similar(proposed_stem):
        return proposed_stem

    for n in range(2, 21):
        candidate = f'{proposed_stem}_{n}'
        if not is_too_similar(candidate):
            return candidate

    return None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "discover or taken or unique_stem"
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add file discovery and filename uniqueness checks"
```

---

### Task 6: Ollama LLM integration

**Files:**
- Modify: `rename.py`
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_rename.py`:

```python
from unittest.mock import patch, MagicMock
from rename import check_ollama, summarize_with_llm


def test_check_ollama_success():
    with patch('rename.requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        assert check_ollama() is True


def test_check_ollama_failure():
    with patch('rename.requests.get', side_effect=Exception('connection refused')):
        assert check_ollama() is False


def test_summarize_returns_clean_title():
    with patch('rename.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {
            'response': '  主角逆襲成功贏回尊嚴  '
        }
        result = summarize_with_llm('some content', 'qwen2.5')
        assert result == '主角逆襲成功贏回尊嚴'


def test_summarize_strips_illegal_chars():
    with patch('rename.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {'response': '標題/有:非法*字元'}
        result = summarize_with_llm('content', 'qwen2.5')
        assert '/' not in result
        assert ':' not in result
        assert '*' not in result


def test_summarize_truncates_at_30_cjk():
    with patch('rename.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {'response': '一' * 40}
        result = summarize_with_llm('content', 'qwen2.5')
        assert result == '一' * 30


def test_summarize_returns_none_on_empty_response():
    with patch('rename.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {'response': '   '}
        result = summarize_with_llm('content', 'qwen2.5')
        assert result is None


def test_summarize_returns_none_on_request_error():
    with patch('rename.requests.post', side_effect=Exception('timeout')):
        result = summarize_with_llm('content', 'qwen2.5')
        assert result is None


def test_summarize_sends_correct_prompt():
    with patch('rename.requests.post') as mock_post:
        mock_post.return_value.json.return_value = {'response': '標題'}
        summarize_with_llm('文章內容', 'qwen2.5')
        call_kwargs = mock_post.call_args[1]['json']
        assert '文章命名助手' in call_kwargs['prompt']
        assert '文章內容' in call_kwargs['prompt']
        assert call_kwargs['model'] == 'qwen2.5'
        assert call_kwargs['stream'] is False
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rename.py -v -k "ollama or summarize or check_ollama"
```

Expected: `ImportError`.

- [ ] **Step 3: Implement Ollama functions**

Add `import requests` at the top of `rename.py` (after existing imports), then append:

```python
import requests

OLLAMA_URL = 'http://localhost:11434'
PROMPT_TEMPLATE = (
    '你是一個文章命名助手。請閱讀以下完整文章內容，理解整體故事主旨，\n'
    '不要只看開頭，然後用不超過30個漢字為這篇文章取一個準確的標題作為檔名。\n'
    '只輸出標題文字，不要加標點符號、副檔名或任何解釋。\n\n'
    '文章內容：\n{content}'
)


def check_ollama() -> bool:
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def summarize_with_llm(content: str, model: str = 'qwen2.5'):
    prompt = PROMPT_TEMPLATE.format(content=content)
    try:
        r = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={'model': model, 'prompt': prompt, 'stream': False},
            timeout=120,
        )
        raw = r.json().get('response', '').strip()
    except Exception:
        return None

    if not raw:
        return None

    cleaned = clean_filename(raw)
    cleaned = truncate_to_30_cjk(cleaned)
    return cleaned if cleaned else None
```

Note: move `import requests` to the top of the file with the other imports.

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "ollama or summarize or check_ollama"
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add Ollama LLM integration with mock-tested summarizer"
```

---

### Task 7: Main orchestration loop

**Files:**
- Modify: `rename.py` (add `main()`)
- Modify: `tests/test_rename.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_rename.py`:

```python
import pytest
from unittest.mock import patch


def test_main_renames_file(tmp_path):
    txt_file = tmp_path / 'random_gibberish_name_123.txt'
    txt_file.write_text('李明是個普通上班族，被老闆欺壓多年後奮起反擊，最終創業成功。', encoding='utf-8')

    with patch('rename.check_ollama', return_value=True), \
         patch('rename.summarize_with_llm', return_value='上班族反擊老闆創業成功'), \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    log_path = tmp_path / '.rename_log.json'
    assert log_path.exists()
    log = json.loads(log_path.read_text(encoding='utf-8'))
    entry = log.get('random_gibberish_name_123.txt')
    assert entry is not None
    assert entry['status'] == 'done'
    assert entry['new_name'] == '上班族反擊老闆創業成功.txt'
    assert (tmp_path / '上班族反擊老闆創業成功.txt').exists()
    assert not txt_file.exists()


def test_main_skips_already_done(tmp_path):
    txt_file = tmp_path / '已完成.txt'
    txt_file.write_text('content', encoding='utf-8')
    log_path = tmp_path / '.rename_log.json'
    log_path.write_text(json.dumps({
        '已完成.txt': {'old_name': '已完成.txt', 'new_name': '新名.txt',
                      'status': 'done', 'timestamp': '2026-01-01T00:00:00+00:00'}
    }), encoding='utf-8')

    call_count = {'n': 0}
    def mock_summarize(content, model='qwen2.5'):
        call_count['n'] += 1
        return '新名字'

    with patch('rename.check_ollama', return_value=True), \
         patch('rename.summarize_with_llm', side_effect=mock_summarize), \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    assert call_count['n'] == 0


def test_main_logs_error_on_llm_failure(tmp_path):
    txt_file = tmp_path / 'fail_me.txt'
    txt_file.write_text('content', encoding='utf-8')

    with patch('rename.check_ollama', return_value=True), \
         patch('rename.summarize_with_llm', return_value=None), \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    log = json.loads((tmp_path / '.rename_log.json').read_text(encoding='utf-8'))
    assert log['fail_me.txt']['status'].startswith('error:')
    assert log['fail_me.txt']['new_name'] is None
    assert txt_file.exists()  # original file untouched


def test_main_exits_on_invalid_folder(tmp_path):
    with patch('rename.check_ollama', return_value=True), \
         patch('sys.argv', ['rename.py', str(tmp_path / 'nonexistent')]):
        from rename import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_logs_error_on_read_failure(tmp_path):
    txt_file = tmp_path / 'unreadable.txt'
    txt_file.write_text('content', encoding='utf-8')

    original_open = open
    def patched_open(path, *args, **kwargs):
        if str(path) == str(txt_file):
            raise OSError('permission denied')
        return original_open(path, *args, **kwargs)

    with patch('rename.check_ollama', return_value=True), \
         patch('builtins.open', side_effect=patched_open), \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    log = json.loads((tmp_path / '.rename_log.json').read_text(encoding='utf-8'))
    assert log['unreadable.txt']['status'].startswith('error:')
    assert log['unreadable.txt']['new_name'] is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rename.py -v -k "test_main"
```

Expected: `ImportError: cannot import name 'main'`.

- [ ] **Step 3: Implement main()**

Append to `rename.py`:

```python
def main():
    parser = argparse.ArgumentParser(
        description='Rename .txt files using a local LLM to generate Chinese filenames.'
    )
    parser.add_argument('folder', help='Path to the folder containing .txt files')
    args = parser.parse_args()

    folder = args.folder
    if not os.path.isdir(folder):
        print(f'Error: {folder!r} is not a directory.', file=sys.stderr)
        sys.exit(1)

    if not check_ollama():
        print(
            'Error: Ollama is not running. Start it with: ollama serve',
            file=sys.stderr
        )
        sys.exit(1)

    log_path = os.path.join(folder, '.rename_log.json')
    log = load_log(log_path)

    files = discover_files(folder, log)
    if not files:
        print('No new files to process.')
        return

    print(f'Found {len(files)} file(s) to process.')

    for filename in files:
        old_path = os.path.join(folder, filename)
        print(f'Processing: {filename}')

        try:
            with open(old_path, 'r', encoding='utf-8', errors='replace') as f:
                raw_content = f.read()
        except OSError as e:
            print(f'  Error reading file: {e}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, f'error: {e}')
            save_log(log_path, log)
            continue

        content = strip_preamble(raw_content)

        new_stem = summarize_with_llm(content)
        if not new_stem:
            print(f'  Error: LLM returned empty response', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, 'error: LLM returned empty response')
            save_log(log_path, log)
            continue

        taken_stems = build_taken_stems(folder, log)
        unique_stem = find_unique_stem(new_stem, taken_stems)
        if unique_stem is None:
            msg = 'error: could not find unique filename after 20 attempts'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue

        new_filename = unique_stem + '.txt'
        new_path = os.path.join(folder, new_filename)

        if os.path.exists(new_path):
            msg = f'error: target path already exists: {new_filename}'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue

        try:
            os.rename(old_path, new_path)
        except OSError as e:
            msg = f'error: rename failed: {e}'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue

        log[filename] = make_log_entry(filename, new_filename, 'done')
        save_log(log_path, log)
        print(f'  Renamed to: {new_filename}')

    done = sum(1 for v in log.values() if v.get('status') == 'done')
    errors = sum(1 for v in log.values() if v.get('status', '').startswith('error'))
    print(f'\nDone. {done} renamed, {errors} error(s).')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_rename.py -v -k "test_main"
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add rename.py tests/test_rename.py
git commit -m "feat: add main orchestration loop — script is now functional"
```

---

### Task 8: Setup verification

**Files:**
- No code changes

- [ ] **Step 1: Install Ollama**

```bash
brew install ollama
```

Or download from https://ollama.com if brew is unavailable.

- [ ] **Step 2: Pull the Chinese-capable model**

```bash
ollama pull qwen2.5
```

Expected: model downloads (may take several minutes, ~4GB).

- [ ] **Step 3: Start Ollama server**

```bash
ollama serve
```

Run in a separate terminal tab. Leave it running.

- [ ] **Step 4: Run smoke test on novel-tc folder**

```bash
source venv/bin/activate
python rename.py ./novel-tc
```

Expected: files begin renaming, log appears at `novel-tc/.rename_log.json`.

- [ ] **Step 5: Verify idempotency — run again**

```bash
python rename.py ./novel-tc
```

Expected: `No new files to process.` (or only processes files that errored on first run).

- [ ] **Step 6: Final commit**

```bash
git add rename.py tests/ requirements.txt .gitignore
git commit -m "chore: verify setup complete, tool functional end-to-end"
```
