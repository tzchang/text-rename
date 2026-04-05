#!/usr/bin/env python3
import argparse
import difflib
import json
import os
import re
import sys
import time
import requests
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
    name = re.sub(r'[\n\r/\\:*?"<>|]', '', name)
    return name


PREAMBLE_KEYWORDS = [
    '廣告', '版權', '作者：', '出版', 'All Rights Reserved',
    '禁止轉載', '付費', '訂閱', '瑪麗',
    # Removed 關注/點贊/轉發: too common in story text to be reliable header indicators
]


def strip_preamble(content: str, debug: bool = False) -> str:
    paragraphs = content.split('\n\n')
    result = []
    for i, para in enumerate(paragraphs):
        if i < 5 and len(para) <= 3000:
            if i == 0 and 'LZ' in para:
                if debug:
                    print(f'  [strip] para[{i}] removed (LZ): {para[:60]!r}', file=sys.stderr)
                continue
            matched = [kw for kw in PREAMBLE_KEYWORDS if kw in para]
            if matched:
                if debug:
                    print(f'  [strip] para[{i}] removed (keywords {matched}): {para[:60]!r}', file=sys.stderr)
                continue
        result.append(para)
    if debug:
        print(f'  [strip] {len(paragraphs)} paragraphs → {len(result)} kept', file=sys.stderr)
    cleaned = '\n\n'.join(result)
    if len(cleaned) > 6000:
        cleaned = cleaned[:6000]
    return cleaned


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


def discover_files(folder: str, log: dict) -> list:
    done_keys = {k for k, v in log.items() if v.get('status') == 'done'}
    done_new_names = {
        v['new_name'] for v in log.values()
        if v.get('status') == 'done' and v.get('new_name')
    }
    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith('.txt')
        and f not in done_keys
        and f not in done_new_names
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


OLLAMA_URL = 'http://localhost:11434'
SUMMARY_PROMPT = (
    '總結劇情重點, 你必須只輸出一句摘要，絕對不要提供多個選擇，'
    '絕對不能輸出任何解釋、說明、標點符號或其他文字。'
    ' 輸出必須是單行純文字，不超過15個漢字。'
)

_TITLE_PREFIX_RE = re.compile(
    r'^(?:标题[可以是：:]+|標題[可以是：:]+|题目[是：:]+|'
    r'这篇文章[的可以]?[叫命名标题]+[是為为：:]+|'
    r'###\s*|【[^】]*】|《[^》]*》\s*(?:这个|這個).*)',
    re.DOTALL,
)
_GUILLEMETS_RE = re.compile(r'[《「『【]([^》」』】\n]{1,30})[》」』】]')
_CHAPTER_RE = re.compile(r'^第[0-9０-９一二三四五六七八九十百千]+[章回]')


def extract_title(raw: str) -> str:
    # Extract content inside guillemets/brackets if present
    m = _GUILLEMETS_RE.search(raw)
    if m:
        return m.group(1).strip()
    # Strip known verbose prefixes
    cleaned = _TITLE_PREFIX_RE.sub('', raw).strip()
    # Take only the first line
    cleaned = cleaned.split('\n')[0].strip()
    # Drop trailing explanation after first Chinese sentence-ending or space+text
    cleaned = re.split(r'[，。！？\s](?=[这這此该該])', cleaned)[0].strip()
    return cleaned


def is_valid_title(title: str) -> bool:
    if not title:
        return False
    # Reject bare chapter headings like 第１章, 第一節
    if _CHAPTER_RE.match(title):
        return False
    return True


def check_ollama() -> bool:
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        return r.status_code == 200
    except Exception:
        return False


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


def summarize_with_llm(content: str, model: str = 'gemma4'):
    turn1_content = f'請閱讀以下文章：\n\n{content}'
    try:
        r1 = requests.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': turn1_content}],
                'stream': False,
                'think': False,
                'keep_alive': 0,
                'options': {'temperature': 0.1, 'num_predict': 500, 'num_ctx': 32768},
            },
            timeout=120,
        )
        r1.raise_for_status()
        r1_json = r1.json()
        turn1_reply = r1_json.get('message', {}).get('content', '').strip()
    except Exception as e:
        print(f'  [Turn1 error] {e}', file=sys.stderr)
        return None

    turn1_tail = '\n'.join(turn1_reply.splitlines()[-2:])
    print(f'  [Turn1 tail] {turn1_tail!r}', file=sys.stderr)

    if not turn1_reply:
        done_reason = r1_json.get('done_reason', 'unknown')
        prompt_eval_count = r1_json.get('prompt_eval_count', 'unknown')
        eval_count = r1_json.get('eval_count', 'unknown')
        raw_content = r1_json.get('message', {}).get('content', '')
        print(f'  [Turn1 empty] done_reason={done_reason!r} prompt_tokens={prompt_eval_count} output_tokens={eval_count}', file=sys.stderr)
        print(f'  [Turn1 raw_content] len={len(raw_content)} repr={raw_content[:80]!r}', file=sys.stderr)
        return None

    try:
        r2 = requests.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': model,
                'messages': [
                    {'role': 'user', 'content': turn1_content},
                    {'role': 'assistant', 'content': turn1_reply},
                    {'role': 'user', 'content': SUMMARY_PROMPT},
                ],
                'stream': False,
                'think': False,
                'keep_alive': 0,
                'options': {
                    'temperature': 0.1,
                    'num_predict': 40,
                    'num_ctx': 32768,
                    'stop': ['\n', '。\n', '\n\n', '，这', '，這', ' 这', ' 這'],
                },
            },
            timeout=120,
        )
        r2.raise_for_status()
        raw = r2.json().get('message', {}).get('content', '').strip()
    except Exception as e:
        print(f'  [Turn2 error] {e}', file=sys.stderr)
        return None

    print(f'  [LLM raw] {raw!r}', file=sys.stderr)

    if not raw:
        return None

    title = extract_title(raw)
    title = clean_filename(title)
    title = truncate_to_30_cjk(title)
    return title if is_valid_title(title) else None


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

        content = strip_preamble(raw_content, debug=True)
        print(f'  [content] {len(content)} chars after strip_preamble', file=sys.stderr)

        if len(content) < 100:
            msg = f'error: content too short ({len(content)} chars)'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            continue

        new_stem = summarize_with_llm(content)
        if not new_stem:
            print(f'  Error: LLM returned empty response', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, 'error: LLM returned empty response')
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue

        taken_stems = build_taken_stems(folder, log)
        unique_stem = find_unique_stem(new_stem, taken_stems)
        if unique_stem is None:
            msg = 'error: could not find unique filename after 20 attempts'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue

        new_filename = unique_stem + '.txt'
        new_path = os.path.join(folder, new_filename)

        if os.path.exists(new_path):
            msg = f'error: target path already exists: {new_filename}'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue

        try:
            os.rename(old_path, new_path)
        except OSError as e:
            msg = f'error: rename failed: {e}'
            print(f'  {msg}', file=sys.stderr)
            log[filename] = make_log_entry(filename, None, msg)
            save_log(log_path, log)
            if not wait_for_model_unloaded('gemma4'):
                print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                      file=sys.stderr)
            continue

        log[filename] = make_log_entry(filename, new_filename, 'done')
        save_log(log_path, log)
        print(f'  Renamed to: {new_filename}')
        if not wait_for_model_unloaded('gemma4'):
            print('  Warning: gemma4 still loaded after 30s, continuing anyway',
                  file=sys.stderr)

    done = sum(1 for v in log.values() if v.get('status') == 'done')
    errors = sum(1 for v in log.values() if v.get('status', '').startswith('error'))
    print(f'\nDone. {done} renamed, {errors} error(s).')


if __name__ == '__main__':
    main()
