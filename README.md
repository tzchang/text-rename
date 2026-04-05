# text-rename

Automatically renames `.txt` files using a local LLM to generate concise Chinese titles.

## How It Works

1. Scans a folder for `.txt` files
2. Strips boilerplate preamble (ads, copyright notices) from short header paragraphs and truncates content to 6000 characters; files with fewer than 100 characters of content are skipped
3. Sends the content to a local Ollama model using a two-turn conversation:
   - **Turn 1** — model reads the article and responds freely
   - **Turn 2** — model is asked to produce a Chinese title (≤15 characters) based on its reading
4. Renames the file using the generated title
5. Waits for the model to unload from memory before processing the next file
6. Logs every rename to `.rename_log.json` in the target folder — already-processed files are skipped on subsequent runs

## Requirements

- Python 3.13+
- [Ollama](https://ollama.com/) running locally with `gemma4` pulled

## Setup

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate
pip install -r requirements.txt
ollama pull gemma4
```

## Usage

```bash
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

python rename.py /path/to/folder
```

The script is idempotent — run it multiple times safely. Files already logged as `done` are skipped; files that previously errored are retried.

## Duplicate Handling

If the LLM generates a title too similar (>80% similarity via `difflib`) to an existing filename, a numeric suffix is appended (`_2`, `_3`, … `_20`). If no unique name can be found, the file is skipped and logged as an error.

## Log Format

`.rename_log.json` in the target folder:

```json
{
  "original_filename.txt": {
    "old_name": "original_filename.txt",
    "new_name": "生成的中文標題.txt",
    "status": "done",
    "timestamp": "2026-04-03T12:00:00+00:00"
  }
}
```

## Running Tests

```bash
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate

pytest
```
