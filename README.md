# Screenshot Declutterer

A simple macOS tool to quickly sort and trash the screenshots cluttering your Desktop.

## What it does

Opens a local webpage showing all your Desktop screenshots as thumbnails. Drag a screenshot **left** to keep it, **right** to trash it. When you're done sorting, click **Done** (or let it auto-trigger) — you'll get a confirmation dialog before anything moves to the Trash. Files are never permanently deleted; they go to macOS Trash so you can recover them if needed.

## Requirements

- macOS
- Python 3.9+

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Your browser opens automatically at `http://localhost:5000`.

## How it works

- Scans `~/Desktop` for files matching `Screenshot*.png` (top-level only)
- Serves them via a local Flask server — nothing leaves your machine
- Drag interaction is handled entirely in the browser with vanilla JavaScript
- Trashing is done via [`send2trash`](https://github.com/arsenetar/send2trash), which uses the native macOS Trash

## License

MIT — see [LICENSE](LICENSE)
