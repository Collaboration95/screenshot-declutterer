"""FE-038 browser regression and isolated screenshot-copy validation.

Default: synthetic fixture and public UI evidence under docs/assets/similar-screenshots.
--copy-from ~/Desktop: copies up to 20 images, uses private gitignored output only.
The server's Trash adapter unlinks disposable fixture copies; never source images.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import capture_ui_baseline as baseline
import check_cleanup_ui as cleanup
import demo_fixtures
from PIL import Image, ImageDraw

ROOT = baseline._REPO_ROOT / ".cache" / "similarity-fixtures"
OUT = baseline._REPO_ROOT / "docs" / "assets" / "similar-screenshots"
ANCHOR = "Screenshot similarity-anchor.png"
BOOTSTRAP = """
import sys
from datetime import timedelta
from pathlib import Path
from werkzeug.serving import make_server
import ss_dcl.app as app
from ss_dcl import usage
now = usage.utc_now()
usage.read_usage = lambda paths: {
    path: usage.UsageMetadata(now-timedelta(minutes=32), now-timedelta(minutes=30))
    for path in paths if path.name.startswith('Screenshot similarity-')
}
# All operations are restricted to this generated fixture by AppServer env.
app.send2trash = lambda path: Path(path).unlink()
@app.app.post('/__test/disappear')
def disappear():
    (app.DESKTOP / 'Screenshot similarity-resized.png').unlink(missing_ok=True)
    return {'ok': True}
make_server('127.0.0.1', int(sys.argv[1]), app.app, threaded=True).serve_forever()
"""


def fixtures(root: Path, copy_from: Path | None) -> dict:
    manifest = demo_fixtures.write_workspace(root, force=True)
    desktop = root / demo_fixtures.DESKTOP_DIR
    tracked = root / demo_fixtures.TRACKED_DIR
    anchor = desktop / ANCHOR
    if copy_from:
        originals = [
            p
            for p in sorted(copy_from.glob("Screenshot*.*"))
            if p.is_file()
            and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff", ".bmp")
            and p.resolve().is_relative_to(copy_from.resolve())
        ][:20]
        if not originals:
            raise baseline.CaptureError("No supported screenshots found in the requested source")
        # Neutral names ensure logs/reports do not disclose personal filenames.
        for index, source in enumerate(originals):
            shutil.copy2(source, desktop / f"Screenshot private-{index:02d}{source.suffix.lower()}")
        # Preserve original bytes for the exact duplicate, despite this neutral name.
        shutil.copy2(originals[0], anchor)
        manifest["personal_copy_count"] = len(originals)
    else:
        shutil.copy2(desktop / demo_fixtures.CATALOGUE[5].name, anchor)
    shutil.copy2(anchor, tracked / ANCHOR)
    with Image.open(anchor) as source_image:
        image = source_image.convert("RGB")
        image.save(desktop / "Screenshot similarity-reencoded.jpg", quality=90)
        image.resize((image.width * 3 // 4, image.height * 3 // 4), Image.Resampling.LANCZOS).save(
            desktop / "Screenshot similarity-resized.png"
        )
        cursor = image.copy()
        x, y = image.width // 2, image.height // 2
        ImageDraw.Draw(cursor).polygon([(x, y), (x, y + 15), (x + 10, y + 10)], fill="black")
        cursor.save(desktop / "Screenshot similarity-cursor.png")
    # Start every file in Unsorted; real settings/state are never read.
    state = root / demo_fixtures.RUNTIME_DIR / demo_fixtures.STATE_DIR / "state.json"
    state.write_text(json.dumps({"decisions": {}}))
    return manifest


def interact(page: baseline.CdpSession, base_url: str) -> None:
    page.call("Page.navigate", {"url": base_url})
    cleanup.ready(page)
    page.evaluate(
        f"window.anchor = () => [...document.querySelectorAll('.card')].find(c=>"
        f"c.dataset.source === 'Desktop' && c.dataset.filename === {json.dumps(ANCHOR)});"
        "window.peers = kind => (anchor().similarityMatches || []).filter(m=>m.kind===kind);"
        "window.badge = kind => anchor().querySelector('.similarity-'+kind);"
        "window.clickBadge = kind => badge(kind).click();"
    )
    cleanup.check(
        page,
        "Boolean(badge('identical')) && peers('identical').some(m=>m.source!=='Desktop')",
        "identical badge distinguishes same-name files across sources",
    )
    cleanup.check(
        page,
        "anchor().classList.contains('cleanup-card')",
        "similarity badges coexist with cleanup review",
    )
    cleanup.check(
        page,
        "Boolean(badge('similar')) && peers('similar').some(m=>m.name.ends"
        "With('.jpg')) && peers('similar').some(m=>m.name.includes('resize"
        "d'))",
        "reencoded and resized screenshots are near-match candidates",
    )
    page.evaluate("window.before=JSON.stringify([...decisions]); clickBadge('identical')")
    cleanup.check(
        page,
        "selectedCards.size === peers('identical').length+1 && !batchBar.h"
        "idden && cleanupFooter.hidden && JSON.stringify([...decisions])=="
        "=before",
        "badge selects anchor and direct identical peers without making decisions",
    )
    cleanup.check(
        page,
        "dragSelection(anchor()).length === selectedCards.size",
        "cleanup-card drag honors explicit similarity selection",
    )
    page.evaluate(
        "window.groupSize=selectedCards.size; anchor().querySelector('.cleanup-select').click()"
    )
    cleanup.check(
        page,
        "selectedCards.size===groupSize-1 && !selectedCards.has(anchor()) && !batchBar.hidden",
        "unchecking a selected cleanup match preserves the rest of the board selection",
    )
    page.evaluate("anchor().querySelector('.cleanup-select').click()")
    cleanup.check(
        page, "selectedCards.size===groupSize", "rechecking restores the direct selection"
    )
    page.evaluate("window.expected=selectedCards.size; batchTrashBtn.click()")
    cleanup.check(
        page,
        "cardsTrash.querySelectorAll('.card').length===expected && selectedCards.size===expected",
        "batch queue moves only selected matches and retains selection",
    )
    page.evaluate("for(let i=0;i<expected;i++) performUndo(); clearSelection()")
    cleanup.check(
        page,
        "cardsTrash.querySelectorAll('.card').length===0 && selectedCards."
        "size===0 && batchBar.hidden",
        "undo restores each match through the existing workflow",
    )
    page.evaluate("clickBadge('similar')")
    cleanup.check(
        page,
        "selectedCards.size===peers('similar').length+1 && "
        "[...selectedCards].every(c=>c===anchor() || peers('similar').some(m=>"
        "SsDcl.fileKey(m)===cleanupKey(c)))",
        "near badge selects only its direct peers, with no transitive expansion",
    )
    page.evaluate(
        "clearSelection(); window.ordinaryMatch=document.querySelector("
        "'.card:not(.cleanup-card) .similarity-identical'); ordinaryMatch.click()"
    )
    cleanup.check(
        page,
        "selectedCards.size===expected && [...selectedCards].some(c=>"
        "c.classList.contains('cleanup-card'))",
        "ordinary-card badge can select matches inside the cleanup batch",
    )
    page.evaluate(
        "clickBadge('identical'); window.dragged=anchor(); window.dt=new D"
        "ataTransfer(); dragged.dispatchEvent(new DragEvent('dragstart',{b"
        "ubbles:true,dataTransfer:dt})); colKeep.dispatchEvent(new DragEve"
        "nt('drop',{bubbles:true,dataTransfer:dt})); dragged.dispatchEvent"
        "(new DragEvent('dragend',{bubbles:true,dataTransfer:dt}));"
    )
    cleanup.check(
        page,
        "cardsKeep.querySelectorAll('.card').length===expected && selectedCards.size===expected",
        "drag across columns moves the selected matches",
    )
    page.evaluate(
        "for(let i=0;i<expected;i++) performUndo(); clearSelection(); open"
        "RenameModal(anchor()); renameInput.value='Screenshot similarity-r"
        "enamed.png'; renameConfirm.click()"
    )
    page.wait_for(
        "Boolean(document.querySelector('[data-filename=\"Screenshot similarity-renamed.png\"]'))",
        "rename",
    )
    cleanup.check(
        page,
        "[...document.querySelectorAll('.card')].filter(c=>c.dataset.sourc"
        "e!=='Desktop').some(c=>(c.similarityMatches||[]).some(m=>m.name=="
        "='Screenshot similarity-renamed.png'))",
        "rename updates peer references immediately",
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "loadingMsg.hidden && Boolean(document.querySelector('[data-filena"
        'me="Screenshot similarity-renamed.png"] .similarity-identical\'))',
        "renamed rescan",
    )
    page.evaluate(
        "window.renamed=document.querySelector('[data-filename=\"Screenshot"
        " similarity-renamed.png\"]'); renamed.querySelector('.similarity-i"
        "dentical').click();"
    )
    cleanup.check(page, "selectedCards.size === expected", "matches survive rename and refresh")
    page.evaluate("batchTrashBtn.click(); doneBtn.click(); modalConfirm.click()")
    page.wait_for(
        "!document.querySelector('[data-filename=\"Screenshot similarity-re"
        "named.png\"]') && !document.querySelector('#cards-trash .card')",
        "fixture-only Done",
    )
    cleanup.check(
        page,
        "![...document.querySelectorAll('.similarity-identical')].some(b=>"
        "b.title.includes('0 identical'))",
        "Done removes deleted peers and updates remaining badges",
    )
    page.evaluate("fetch('/__test/disappear',{method:'POST'})", await_promise=True)
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "loadingMsg.hidden && !document.querySelector('[data-filename=\"Scr"
        "eenshot similarity-resized.png\"]')",
        "disappeared file rescan",
    )
    cleanup.check(
        page,
        "[...document.querySelectorAll('.card')].every(c=>(c.similarityMat"
        "ches||[]).every(m=>!m.name.includes('resized')))",
        "refresh removes disappeared matches",
    )
    if page.exceptions:
        raise baseline.CaptureError(f"Browser errors: {page.exceptions}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy-from", type=Path)
    args = parser.parse_args()
    personal = args.copy_from is not None
    root = ROOT.with_name("similarity-personal-fixtures") if personal else ROOT
    out = ROOT.with_name("similarity-personal-report") if personal else OUT
    manifest = fixtures(root, args.copy_from)
    chrome = baseline.find_chrome()
    if not chrome:
        raise baseline.CaptureError("Chrome is required")
    out.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        server = stack.enter_context(baseline.AppServer(root, bootstrap=BOOTSTRAP))
        profile = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="ss-dcl-similarity-"))
        )
        browser = stack.enter_context(baseline.ChromeSession(chrome, profile))
        page = browser.new_page()
        stack.callback(page.close)
        page.call("Page.enable")
        page.call("Runtime.enable")
        screenshots = []
        for theme in ("light", "dark"):
            injected = page.call(
                "Page.addScriptToEvaluateOnNewDocument", {"source": baseline._theme_source(theme)}
            )
            for width, height in ((1440, 900), (320, 900)):
                page.call(
                    "Emulation.setDeviceMetricsOverride",
                    {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                )
                page.call("Page.navigate", {"url": server.base_url})
                cleanup.ready(page)
                cleanup.check(
                    page,
                    "document.documentElement.scrollWidth<=innerWidth",
                    f"{width}px {theme}: no horizontal overflow",
                )
                cleanup.check(
                    page,
                    "[...document.querySelectorAll('.similarity-badge')].filter(b=>b.g"
                    "etBoundingClientRect().width>0).every(b=>{const r=b.getBoundingCl"
                    "ientRect();return r.left>=0&&r.right<=innerWidth})",
                    f"{width}px {theme}: badges fit",
                )
                page.evaluate("document.querySelector('.similarity-identical').focus()")
                page.call(
                    "Input.dispatchKeyEvent",
                    {
                        "type": "keyDown",
                        "key": "Enter",
                        "code": "Enter",
                        "windowsVirtualKeyCode": 13,
                        "text": "\r",
                        "unmodifiedText": "\r",
                    },
                )
                page.call(
                    "Input.dispatchKeyEvent",
                    {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
                )
                cleanup.check(
                    page,
                    "selectedCards.size>=2 && !batchBar.hidden",
                    f"{width}px {theme}: keyboard badge selection",
                )
                filename = f"{width}x{height}-selected-{theme}.png"
                (out / filename).write_bytes(
                    base64.b64decode(
                        page.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})[
                            "data"
                        ]
                    )
                )
                screenshots.append(filename)
            page.call(
                "Page.removeScriptToEvaluateOnNewDocument", {"identifier": injected["identifier"]}
            )
        page.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )
        interact(page, server.base_url)
        report = {
            "browser": browser.version(),
            "personal_copy_count": manifest.get("personal_copy_count", 0),
            "interaction_checks": "passed",
            "screenshots": screenshots,
        }
        (out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"All similarity UI checks passed; output: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except baseline.CaptureError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
