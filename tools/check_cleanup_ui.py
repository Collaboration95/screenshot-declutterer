"""Issue #118 browser regression checks and deterministic, non-personal captures.

Run: .venv/bin/python tools/check_cleanup_ui.py
Uses the existing demo/Chrome harness, fake usage dates and isolated state.
The AI server stays offline. No real Desktop files or Spotlight data are read.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import capture_ui_baseline as baseline
import demo_fixtures

NOW = datetime(2026, 10, 8, 9, 30, tzinfo=timezone.utc)
OUT = baseline._REPO_ROOT / "docs" / "assets" / "cleanup-suggestions"
ROOT = baseline._REPO_ROOT / ".cache" / "cleanup-fixtures"
BOOTSTRAP = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))
from check_cleanup_ui import serve
serve(int(sys.argv[1]))
"""


def serve(port: int, *, batches: bool = False) -> None:
    from flask import jsonify
    from werkzeug.serving import make_server

    import ss_dcl.app as flask_app
    from ss_dcl import usage

    root = flask_app.DESKTOP.parent
    original = root / demo_fixtures.DESKTOP_DIR / demo_fixtures.CATALOGUE[5].name
    duplicate = root / demo_fixtures.TRACKED_DIR / original.name
    suggested = root / demo_fixtures.DESKTOP_DIR / demo_fixtures.CATALOGUE[16].name
    duplicate_inode = duplicate.stat().st_ino
    # Key fake activity by inode so a fixture rename preserves the signal.
    records = {
        path.stat().st_ino: usage.UsageMetadata(
            NOW - timedelta(minutes=age + opened), NOW - timedelta(minutes=age)
        )
        for path, age, opened in [(original, 28, 2), (duplicate, 21, 3), (suggested, 18, 4)]
    }
    if batches:
        paths = sorted(root.joinpath(demo_fixtures.DESKTOP_DIR).glob("Screenshot*.*"))
        paths += sorted(root.joinpath(demo_fixtures.TRACKED_DIR).glob("Screenshot*.*"))
        for path in paths:
            if len(records) == 17:
                break
            records.setdefault(
                path.stat().st_ino,
                usage.UsageMetadata(NOW - timedelta(minutes=32), NOW - timedelta(minutes=30)),
            )
    usage.utc_now = lambda: NOW
    usage.read_usage = lambda paths: {
        path: records.get(path.stat().st_ino, usage.UsageMetadata()) for path in paths
    }

    @flask_app.app.post("/__test/later-open")
    def later_open():
        inode = original.stat().st_ino
        records[inode] = usage.UsageMetadata(records[inode].created_at, NOW - timedelta(minutes=1))
        return jsonify(ok=True)

    @flask_app.app.post("/__test/disappear")
    def disappear():
        for path in duplicate.parent.glob("Screenshot*.*"):
            if path.stat().st_ino == duplicate_inode:
                path.unlink()
        return jsonify(ok=True)

    # Actual trash is never called by the browser checks, even on regression.
    def no_trash(path):
        raise AssertionError(f"Unexpected disk-trash request: {path}")

    flask_app.send2trash = no_trash
    make_server("127.0.0.1", port, flask_app.app, threaded=True).serve_forever()


def check(page: baseline.CdpSession, expression: str, label: str) -> None:
    if not page.evaluate(f"Boolean({expression})"):
        raise baseline.CaptureError(f"FAIL: {label}")
    print(f"PASS: {label}", flush=True)


def ready(page: baseline.CdpSession) -> None:
    page.wait_for(baseline._PAGE_READY, "fixture board")
    page.evaluate("new Promise(resolve => setTimeout(resolve, 350))", await_promise=True)


def controls(page: baseline.CdpSession) -> None:
    page.evaluate(
        "window.candidates = () => [...document.querySelectorAll('#cleanup-cards .card')];"
        "window.ordinary = () => [...document.querySelectorAll('#ordinary-unsorted .card')];"
        "window.click = selector => document.querySelector(selector).click();"
        "window.review = () => candidates().filter(c => "
        "c.querySelector('.cleanup-select').checked);"
    )


def focus_footer(page: baseline.CdpSession) -> str:
    page.evaluate("document.getElementById('cleanup-select-all').focus()")
    page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Tab", "code": "Tab"})
    check(page, "document.activeElement === cleanupQueue", "320px footer queue reached by Tab")
    check(
        page,
        "cleanupQueue.getBoundingClientRect().bottom <= innerHeight",
        "320px footer scrolls into view for keyboard review",
    )
    return "Scrolled to the review footer; Queue is focused by keyboard"


def capture_matrix(page: baseline.CdpSession, base_url: str, out: Path) -> list[baseline.Shot]:
    shots = []
    for theme, system in [
        ("light", "light"),
        ("dark", "dark"),
        ("auto", "light"),
        ("auto", "dark"),
    ]:
        injected = page.call(
            "Page.addScriptToEvaluateOnNewDocument", {"source": baseline._theme_source(theme)}
        )
        page.call(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-color-scheme", "value": system}]},
        )
        for width, height in [(1440, 900), (1024, 768), (320, 900)]:
            name = theme if theme != "auto" else f"auto-{system}"
            viewport = baseline.Viewport(f"{width}x{height}", width, height, "cleanup")
            shot = baseline.capture(
                page,
                base_url=base_url,
                viewport=viewport,
                state=baseline.CaptureState("board", "Inline cleanup suggestions"),
                out_dir=out,
                theme=name,
                scale=1,
                settle=0.2,
                timeout=15,
            )
            shots.append(shot)
            check(
                page,
                "document.documentElement.scrollWidth <= innerWidth",
                f"{width}px {name}: no page overflow",
            )
            check(
                page,
                "[...document.querySelectorAll('#cleanup-group button, #cleanup-group "
                "input')].filter(n => !n.closest('[hidden]')).every(n => { const "
                "r=n.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; })",
                f"{width}px {name}: review controls fit",
            )
            if width == 320 and theme != "auto":
                shots.append(
                    baseline.capture(
                        page,
                        base_url=base_url,
                        viewport=viewport,
                        state=baseline.CaptureState(
                            "footer", "Keyboard review footer", prepare=focus_footer
                        ),
                        out_dir=out,
                        theme=name,
                        scale=1,
                        settle=0.2,
                        timeout=15,
                    )
                )
        page.call(
            "Page.removeScriptToEvaluateOnNewDocument", {"identifier": injected["identifier"]}
        )
    return shots


def interactions(page: baseline.CdpSession, base_url: str) -> None:
    page.call(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    page.call("Page.navigate", {"url": base_url})
    ready(page)
    controls(page)
    check(
        page,
        "candidates().length === 3 && review().length === 3",
        "all three cleanup candidates initially selected",
    )
    check(
        page,
        "document.querySelectorAll('.card').length === 21 && new "
        "Set([...document.querySelectorAll('.card')].map(c=>cleanupKey(c))).size === "
        "21",
        "one real card per source-aware identity",
    )
    check(
        page,
        "Number(countUnsorted.textContent) === cardsUnsorted.querySelectorAll('.card').length",
        "cleanup candidates count as Unsorted",
    )
    check(
        page,
        "candidates().every((c,i,a)=>!i || Number(a[i-1].dataset.scanOrder) < "
        "Number(c.dataset.scanOrder))",
        "scan sort order preserved",
    )
    check(
        page,
        "candidates().some(c => candidates().filter(d=>d.dataset.filename === "
        "c.dataset.filename).length === 2)",
        "identical filenames from Desktop and tracked folder",
    )
    page.evaluate(
        "window.initialDecisions = JSON.stringify([...decisions]); window.requestLog "
        "= []; const realFetch=window.fetch; "
        "window.fetch=(url,opts)=>{requestLog.push([url,opts && opts.method || "
        "'GET']); return realFetch(url,opts);};"
    )
    page.evaluate("candidates()[0].querySelector('.cleanup-select').click()")
    check(
        page,
        "review().length === 2 && cleanupSelectAll.indeterminate && !cleanupSelectAll.checked",
        "partial selection and indeterminate Select all",
    )
    check(
        page,
        "selectedCards.size === 0 && batchBar.hidden && "
        "JSON.stringify([...decisions]) === initialDecisions && "
        "!requestLog.some(r=>r[1] === 'PUT')",
        "review selection writes no decisions or board selection",
    )
    page.evaluate("click('#cleanup-select-all'); click('#cleanup-select-all')")
    check(
        page,
        "review().length === 0 && cleanupQueue.disabled && !cleanupSelectAll.indeterminate",
        "zero selection disables queue",
    )
    page.evaluate(
        "click('#cleanup-select-all'); "
        "candidates()[0].querySelector('.cleanup-select').click(); "
        "window.uncheckedKey=cleanupKey(candidates()[0]); sortSelect.value='name'; "
        "sortSelect.dispatchEvent(new Event('change')); "
    )
    page.wait_for(
        "candidates().length === 3 && !loadingMsg.hidden === false", "sorted cleanup cards"
    )
    check(
        page,
        "review().length === 2 && candidates().find(c=>cleanupKey(c) === "
        "uncheckedKey).querySelector('.cleanup-select').checked === false",
        "unchecked choice survives sort rerender",
    )
    page.evaluate("ordinary()[0].click(); window.unrelated=ordinary()[0]")
    check(
        page,
        "selectedCards.size === 1 && !batchBar.hidden && cleanupFooter.hidden && "
        "!cleanupReview.hidden",
        "board selection has the sole active batch bar",
    )
    page.evaluate("click('#cleanup-review')")
    check(
        page,
        "selectedCards.size === 0 && batchBar.hidden && !cleanupFooter.hidden && "
        "review().length === 2",
        "resume review preserves its scoped choices",
    )
    page.evaluate("candidates()[0].querySelector('.btn-preview').click()")
    check(page, "!lightbox.hidden && review().length === 2", "Preview preserves review selection")
    page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape"})
    page.wait_for(
        "lightbox.hidden && document.activeElement === candidates()[0]", "preview focus restoration"
    )
    check(
        page,
        "lightbox.hidden && review().length === 2 && document.activeElement === candidates()[0]",
        "Escape returns focus to the review context",
    )
    page.evaluate("window.kept=candidates()[0]; kept.querySelector('.btn-keep').click()")
    check(
        page,
        "candidates().length === 2 && cardsKeep.contains(kept)",
        "Keep moves the same card and updates cleanup count",
    )
    page.evaluate("click('#undo-btn')")
    check(
        page,
        "candidates().length === 3 && cleanupCards.contains(kept)",
        "per-card undo returns eligible Keep card to cleanup group",
    )
    page.evaluate(
        "window.beforeTrash=cardsTrash.querySelectorAll('.card').length; "
        "requestLog.length=0; click('#cleanup-queue')"
    )
    check(
        page,
        "cardsTrash.querySelectorAll('.card').length === beforeTrash+2 && "
        "candidates().length === 1 && ordinaryUnsorted.contains(unrelated)",
        "queue moves only the two selected candidates",
    )
    check(
        page,
        "!requestLog.some(r=>r[0] === '/api/done') && statusMsg.textContent.includes('Press Done')",
        "queue writes decisions without trashing files",
    )
    page.evaluate("click('#done-btn')")
    check(page, "!confirmModal.hidden", "Done retains the existing trash confirmation")
    page.evaluate("click('#modal-cancel'); click('#undo-btn'); click('#undo-btn')")
    check(
        page,
        "candidates().length === 3 && review().length === 2",
        "queue undo retains per-card semantics and review choices",
    )
    # Keyboard checkbox operation is dispatched through Chrome, not a JS click.
    page.evaluate("candidates()[0].querySelector('.cleanup-select').focus()")
    page.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": " ", "code": "Space"})
    page.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": " ", "code": "Space"})
    check(page, "review().length === 3", "native cleanup checkbox is keyboard operable")
    page.evaluate(
        "window.dragged=candidates()[0]; const dt=new DataTransfer(); "
        "dragged.dispatchEvent(new "
        "DragEvent('dragstart',{bubbles:true,dataTransfer:dt})); "
        "colTrash.dispatchEvent(new "
        "DragEvent('drop',{bubbles:true,dataTransfer:dt})); "
        "dragged.dispatchEvent(new "
        "DragEvent('dragend',{bubbles:true,dataTransfer:dt}));"
    )
    check(
        page,
        "candidates().length === 0 && cleanupGroup.hidden",
        "cleanup drag selection uses the existing move workflow",
    )
    page.evaluate("click('#undo-btn'); click('#undo-btn'); click('#undo-btn')")
    check(
        page,
        "candidates().length === 3 && review().length === 3",
        "drag undo restores cleanup candidates",
    )
    # Rename the tracked duplicate, preserving the review choice and sibling.
    page.evaluate(
        "window.renamed=candidates().find(c=>c.dataset.source !== 'Desktop'); "
        "renamed.querySelector('.cleanup-select').click(); openRenameModal(renamed); "
        "renameInput.value='Screenshot reviewed-reference.png'; renameConfirm.click()"
    )
    page.wait_for(
        "renamed.dataset.filename === 'Screenshot reviewed-reference.png'", "fixture rename"
    )
    check(
        page,
        "!renamed.querySelector('.cleanup-select').checked && "
        "renamed.querySelector('.card-name').textContent === renamed.dataset.filename",
        "rename preserves unchecked choice and visible filename",
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "candidates().length === 3 && "
        "Boolean(document.querySelector('[data-filename=\"Screenshot "
        "reviewed-reference.png\"]'))",
        "renamed scan",
    )
    check(page, "review().length === 2", "renamed source identity retains review choice on rescan")
    page.evaluate("fetch('/__test/later-open',{method:'POST'})", await_promise=True)
    page.evaluate("refreshScreenshots()")
    page.wait_for("candidates().length === 2 && loadingMsg.hidden", "later recorded open rescan")
    check(
        page,
        "candidates().length === 2",
        "rescan removes a stale candidate after later recorded use",
    )
    page.evaluate("window.beforeDismiss=JSON.stringify([...decisions]); click('#cleanup-dismiss')")
    check(
        page,
        "cleanupGroup.hidden && candidates().length === 0 && "
        "JSON.stringify([...decisions]) === beforeDismiss",
        "Dismiss returns cards to ordinary Unsorted without decisions",
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "document.querySelectorAll('.card').length === 21 && loadingMsg.hidden", "dismissed rescan"
    )
    check(
        page,
        "cleanupGroup.hidden && candidates().length === 0",
        "Dismiss survives explicit refresh in this page session",
    )
    page.call("Page.navigate", {"url": base_url})
    ready(page)
    controls(page)
    check(
        page,
        "candidates().length === 2 && review().length === 2",
        "page reload resets dismissal and review choices",
    )
    check(
        page,
        "candidates().some(c=>c.querySelector('.suggestion-badge')) && "
        "candidates().some(c=>c.dataset.suggestedCategory)",
        "AI filename affordances and category hints coexist with cleanup",
    )
    page.evaluate("fetch('/__test/disappear',{method:'POST'})", await_promise=True)
    page.evaluate("refreshScreenshots()")
    page.wait_for("candidates().length === 1 && loadingMsg.hidden", "disappeared file rescan")
    check(
        page,
        "document.querySelectorAll('.card').length === 20",
        "rescan removes a disappeared tracked file",
    )
    if page.exceptions:
        raise baseline.CaptureError(f"Browser script errors: {page.exceptions}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    chrome = baseline.find_chrome()
    if not chrome:
        raise baseline.CaptureError("Chrome is required for the cleanup UI regression checks")
    manifest = demo_fixtures.write_workspace(ROOT, force=True)
    original = ROOT / demo_fixtures.DESKTOP_DIR / demo_fixtures.CATALOGUE[5].name
    (ROOT / demo_fixtures.TRACKED_DIR / original.name).write_bytes(original.read_bytes())
    args.out.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        server = stack.enter_context(baseline.AppServer(ROOT, bootstrap=BOOTSTRAP))
        profile = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="ss-dcl-cleanup-chrome-"))
        )
        browser = stack.enter_context(baseline.ChromeSession(chrome, profile))
        page = browser.new_page()
        stack.callback(page.close)
        page.call("Page.enable")
        page.call("Runtime.enable")
        shots = capture_matrix(page, server.base_url, args.out)
        interactions(page, server.base_url)
        report = {
            "browser": browser.version(),
            "seed": manifest["seed"],
            "fixed_scan_time": NOW.isoformat(),
            "screenshots": [shot.path.name for shot in shots],
            "interaction_checks": "passed",
        }
        (args.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"All cleanup UI checks passed; screenshots: {args.out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except baseline.CaptureError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
