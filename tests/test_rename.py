# tests/test_rename.py
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


def test_clean_filename_removes_newlines():
    assert clean_filename('標題\n內容') == '標題內容'
    assert clean_filename('第一行\r\n第二行') == '第一行第二行'


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


def test_discover_files_skips_already_renamed(tmp_path):
    # File was renamed in a previous run; its new name is on disk but the log
    # key is the old name, which no longer exists on disk.
    (tmp_path / '好標題.txt').write_text('x')
    (tmp_path / 'b.txt').write_text('x')
    log = {'原始檔名.txt': {'status': 'done', 'new_name': '好標題.txt'}}
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


def test_find_unique_stem_long_exact_match_exhausts_slots():
    # For a 7-char stem, ratio('主角逆襲贏麻了_2', '主角逆襲贏麻了') = 14/16 = 0.875 > 0.8
    # so ALL numbered candidates _2 through _20 are too similar — returns None
    taken = {'主角逆襲贏麻了'}
    result = find_unique_stem('主角逆襲贏麻了', taken)
    assert result is None


def test_find_unique_stem_returns_none_after_20():
    taken = {'新標題'} | {f'新標題_{i}' for i in range(2, 21)}
    result = find_unique_stem('新標題', taken)
    assert result is None


def test_find_unique_stem_skips_similar_numbered_candidate():
    # '新標題_2' is 0.909 similar to '新標題_2x' (> 0.8 threshold)
    # so _2 should be skipped; _3 is not too similar to anything
    taken = {'新標題', '新標題_2x'}
    result = find_unique_stem('新標題', taken)
    assert result == '新標題_3'


from unittest.mock import patch, MagicMock
from rename import check_ollama, summarize_with_llm, wait_for_model_unloaded


def _chat(content):
    """Return a mock requests.Response whose .json() yields a /api/chat reply."""
    m = MagicMock()
    m.json.return_value = {'message': {'role': 'assistant', 'content': content}}
    return m


def test_check_ollama_success():
    with patch('rename.requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        assert check_ollama() is True


def test_check_ollama_failure():
    with patch('rename.requests.get', side_effect=Exception('connection refused')):
        assert check_ollama() is False


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
    with patch('rename.requests.get') as mock_get, \
         patch('rename.time.sleep'):
        mock_get.return_value.json.return_value = {
            'models': [{'name': 'gemma4:latest'}]
        }
        result = wait_for_model_unloaded('gemma4', timeout=1)
        assert result is False
        assert mock_get.call_count >= 1


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
    with patch('rename.requests.get') as mock_get, \
         patch('rename.time.sleep'):
        mock_get.side_effect = Exception('connection refused')
        result = wait_for_model_unloaded('gemma4', timeout=1)
        assert result is False
        assert mock_get.call_count >= 1


def test_summarize_returns_clean_title():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('  主角逆襲成功贏回尊嚴  '),
        ]
        result = summarize_with_llm('some content', 'gemma4')
        assert result == '主角逆襲成功贏回尊嚴'


def test_summarize_strips_illegal_chars():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('標題/有:非法*字元'),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert result is not None, "summarize_with_llm returned None unexpectedly"
        assert '/' not in result
        assert ':' not in result
        assert '*' not in result


def test_summarize_truncates_at_30_cjk():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('一' * 40),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert result == '一' * 30


def test_summarize_returns_none_on_empty_response():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('讀完了'),
            _chat('   '),
        ]
        result = summarize_with_llm('content', 'gemma4')
        assert result is None


def test_summarize_returns_none_on_request_error():
    with patch('rename.requests.post', side_effect=Exception('timeout')):
        result = summarize_with_llm('content', 'gemma4')
        assert result is None


def test_summarize_two_turn_message_structure():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [
            _chat('初步回應'),
            _chat('標題'),
        ]
        summarize_with_llm('文章內容', 'gemma4')

        assert mock_post.call_count == 2

        # Turn 1: single user message with instruction prefix + article, no system prompt
        turn1_payload = mock_post.call_args_list[0][1]['json']
        assert turn1_payload['model'] == 'gemma4'
        assert turn1_payload['messages'][0]['role'] == 'user'
        assert '文章內容' in turn1_payload['messages'][0]['content']
        assert 'system' not in turn1_payload

        # Turn 2: same Turn 1 content + assistant reply + SUMMARY_PROMPT
        from rename import SUMMARY_PROMPT
        turn1_content = turn1_payload['messages'][0]['content']
        turn2_payload = mock_post.call_args_list[1][1]['json']
        assert turn2_payload['model'] == 'gemma4'
        assert turn2_payload['messages'][0] == {'role': 'user', 'content': turn1_content}
        assert turn2_payload['messages'][1] == {'role': 'assistant', 'content': '初步回應'}
        assert turn2_payload['messages'][2] == {'role': 'user', 'content': SUMMARY_PROMPT}

        assert turn1_payload['stream'] is False
        assert turn2_payload['stream'] is False


def test_summarize_default_model_is_gemma4():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('回應'), _chat('標題')]
        summarize_with_llm('content')  # no model argument
        assert mock_post.call_args_list[0][1]['json']['model'] == 'gemma4'
        assert mock_post.call_args_list[1][1]['json']['model'] == 'gemma4'


from rename import extract_title, is_valid_title


def test_extract_title_plain():
    assert extract_title('逆襲成功') == '逆襲成功'


def test_extract_title_guillemets():
    assert extract_title('标题可以是：《逆袭成功》这个标题简洁') == '逆袭成功'


def test_extract_title_prefix_stripped():
    assert extract_title('标题：逆袭成功') == '逆袭成功'


def test_extract_title_first_line_only():
    assert extract_title('逆袭成功\n这篇文章讲述了') == '逆袭成功'


def test_extract_title_trailing_explanation_dropped():
    assert extract_title('逆袭成功 这个标题') == '逆袭成功'


def test_is_valid_title_normal():
    assert is_valid_title('房東惡意漲價後悔不當初') is True


def test_is_valid_title_rejects_chapter_heading_arabic():
    assert is_valid_title('第１章') is False


def test_is_valid_title_rejects_chapter_heading_chinese():
    assert is_valid_title('第一章') is False


def test_is_valid_title_rejects_empty():
    assert is_valid_title('') is False


def test_summarize_uses_keep_alive_zero():
    with patch('rename.requests.post') as mock_post:
        mock_post.side_effect = [_chat('回應'), _chat('標題')]
        summarize_with_llm('content', 'gemma4')
        assert mock_post.call_args_list[0][1]['json']['keep_alive'] == 0
        assert mock_post.call_args_list[1][1]['json']['keep_alive'] == 0


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


import pytest


def test_main_renames_file(tmp_path):
    txt_file = tmp_path / 'random_gibberish_name_123.txt'
    txt_file.write_text('李明是個普通上班族，被老闆欺壓多年後奮起反擊，最終創業成功。' * 5, encoding='utf-8')

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


def test_main_calls_wait_for_memory_after_each_file(tmp_path):
    (tmp_path / 'a.txt').write_text('content a ' * 20, encoding='utf-8')
    (tmp_path / 'b.txt').write_text('content b ' * 20, encoding='utf-8')

    with patch('rename.check_ollama', return_value=True), \
         patch('rename.summarize_with_llm', return_value='標題'), \
         patch('rename.wait_for_model_unloaded', return_value=True) as mock_wait, \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        main()

    assert mock_wait.call_count == 2


def test_main_skips_already_done(tmp_path):
    txt_file = tmp_path / '已完成.txt'
    txt_file.write_text('content', encoding='utf-8')
    log_path = tmp_path / '.rename_log.json'
    log_path.write_text(json.dumps({
        '已完成.txt': {'old_name': '已完成.txt', 'new_name': '新名.txt',
                      'status': 'done', 'timestamp': '2026-01-01T00:00:00+00:00'}
    }), encoding='utf-8')

    call_count = {'n': 0}
    def mock_summarize(content, model='gemma4'):
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


def test_main_exits_when_ollama_not_running(tmp_path):
    with patch('rename.check_ollama', return_value=False), \
         patch('sys.argv', ['rename.py', str(tmp_path)]):
        from rename import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


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
