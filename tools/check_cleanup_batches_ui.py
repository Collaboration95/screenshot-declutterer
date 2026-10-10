"""Issue #120 five-card batch browser checks and non-personal UI evidence.

Run: .venv/bin/python tools/check_cleanup_batches_ui.py
Reuses the isolated demo/Chrome harness; seventeen files have fake usage dates.
"""

from __future__ import annotations

import base64
import contextlib
import json
import sys
import tempfile
from pathlib import Path

import capture_ui_baseline as baseline
import check_cleanup_ui as cleanup
import demo_fixtures

ROOT = baseline._REPO_ROOT / ".cache" / "cleanup-batch-fixtures"
OUT = baseline._REPO_ROOT / "docs" / "assets" / "cleanup-batches"
BOOTSTRAP = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))
from check_cleanup_ui import serve
serve(int(sys.argv[1]), batches=True)
"""


def reset_page(page: baseline.CdpSession, base_url: str) -> None:
    page.evaluate(
        "fetch('/api/state',{method:'PUT',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify({decisions:{}})})",
        await_promise=True,
    )
    page.call("Page.navigate", {"url": base_url})
    cleanup.ready(page)
    cleanup.controls(page)
    page.evaluate(
        "window.eligible = () => cleanupEligibleCards();"
        "window.keys = cards => cards.map(cleanupKey);"
        "window.batchKeys = () => keys(candidates());"
    )


def scroll_context(page: baseline.CdpSession) -> str:
    page.evaluate("cleanupCards.scrollTop=cleanupCards.scrollHeight")
    cleanup.check(
        page,
        "cleanupCards.scrollTop > 0 && (()=>{"
        "const cards=cleanupCards.getBoundingClientRect(), "
        "heading=cleanupHeading.getBoundingClientRect(), "
        "reason=document.getElementById('cleanup-reason').getBoundingClientRect(), "
        "footer=cleanupFooter.getBoundingClientRect();"
        "return heading.top >= 0 && reason.bottom <= cards.top && "
        "footer.top >= cards.bottom && footer.bottom <= innerHeight;})()",
        "scroll keeps heading, reason and queue visible without overlapping cards",
    )
    return "Cleanup cards scrolled; heading, explanation and actions remain visible"


def snapshot(page: baseline.CdpSession, name: str) -> str:
    page.evaluate("new Promise(resolve=>setTimeout(resolve,350))", await_promise=True)
    result = page.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    filename = f"1440x900-{name}-light.png"
    (OUT / filename).write_bytes(base64.b64decode(result["data"]))
    return filename


def interactions(page: baseline.CdpSession, base_url: str) -> list[str]:
    snapshots = []
    page.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": 1440,
            "height": 900,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
    )
    page.evaluate("SsDclTheme.writeMode('light',window)")
    reset_page(page, base_url)
    cleanup.check(
        page,
        "eligible().length === 17 && candidates().length === 5 && review().length === 5 && "
        "cleanupHeading.textContent === 'Cleanup suggestions · 5 shown · 12 more' && "
        "JSON.stringify(batchKeys()) === JSON.stringify(keys(eligible().slice(0,5)))",
        "first five in current sort order, with five shown and twelve waiting",
    )
    cleanup.check(
        page,
        "ordinary().filter(c=>c.dataset.cleanupMatch === 'true').length === 12 && "
        "ordinary().every(c=>!c.classList.contains('selected')) && selectedCards.size === 0",
        "waiting candidates stay ordinary and outside cleanup selection",
    )
    cleanup.check(
        page,
        "![...document.querySelectorAll('.card')].some(c=>"
        "c.textContent.includes('Last recorded')) && "
        "[...document.querySelectorAll('.card[data-source=Desktop]')].every(c=>"
        "Boolean(c.querySelector('.source-tag')) === ([...document.querySelectorAll('.card')]"
        ".filter(d=>d.dataset.filename === c.dataset.filename).length > 1))",
        "no last-open text or routine Desktop badges; duplicates retain source labels",
    )
    page.evaluate(
        "window.firstBatch=batchKeys(); window.beforeChoices=JSON.stringify([...decisions]); "
        "candidates()[0].querySelector('.cleanup-select').click(); window.unchecked=firstBatch[0]"
    )
    cleanup.check(
        page,
        "review().length === 4 && JSON.stringify([...decisions]) === beforeChoices && "
        "cleanupSelectAll.indeterminate",
        "uncheck changes selection without marking Keep",
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for("loadingMsg.hidden && candidates().length === 5", "batch rescan")
    cleanup.check(
        page,
        "JSON.stringify(batchKeys()) === JSON.stringify(firstBatch) && review().length === 4",
        "refresh preserves batch membership and unchecked choices",
    )
    page.evaluate("sortSelect.value='name'; sortSelect.dispatchEvent(new Event('change'))")
    page.wait_for("loadingMsg.hidden && candidates().length === 5", "batch sort")
    cleanup.check(
        page,
        "batchKeys().every(k=>firstBatch.includes(k)) && review().length === 4 && "
        "candidates().every((c,i,a)=>!i || Number(a[i-1].dataset.scanOrder) < "
        "Number(c.dataset.scanOrder))",
        "sort reorders the same batch without advancing or rechecking",
    )
    page.evaluate(
        "window.kept=candidates().find(c=>cleanupKey(c)!==unchecked); moveCard(kept,'keep')"
    )
    cleanup.check(
        page,
        "candidates().length === 4 && review().length === 3 && "
        "cleanupHeading.textContent.endsWith('12 more')",
        "Keep vacates a slot without filling it",
    )
    page.evaluate("performUndo()")
    cleanup.check(
        page,
        "candidates().length === 5 && review().length === 4 && cleanupCards.contains(kept)",
        "current-batch undo restores the same slot and choices",
    )
    page.evaluate(
        "window.requests=[]; window.realFetch=fetch; "
        "window.fetch=(url,opts)=>{requests.push(url); return realFetch(url,opts);}; "
        "click('#cleanup-queue')"
    )
    cleanup.check(
        page,
        "candidates().length === 1 && cardsTrash.querySelectorAll('.card').length === 4 && "
        "!requests.includes('/api/done') && !cleanupNext.disabled",
        "queue affects four displayed selections and enables next batch without Done",
    )
    page.evaluate(
        "window.nextExpected=keys(eligible().filter(c=>"
        "!firstBatch.includes(cleanupKey(c))).slice(0,5)); "
        "click('#cleanup-next')"
    )
    cleanup.check(
        page,
        "JSON.stringify(batchKeys()) === JSON.stringify(nextExpected) && "
        "ordinary().some(c=>cleanupKey(c)===unchecked) && !decisions.has(unchecked) && "
        "cleanupHeading.textContent.endsWith('7 more') && review().length === 5",
        "next five defer unresolved cards in ordinary Unsorted without a Keep decision",
    )
    snapshots.append(snapshot(page, "deferred-next-batch"))
    page.evaluate("performUndo()")
    cleanup.check(
        page,
        "JSON.stringify(batchKeys()) === JSON.stringify(nextExpected) && "
        "ordinary().filter(c=>firstBatch.includes(cleanupKey(c))).length === 2",
        "undo from an earlier batch restores ordinary Unsorted without replacing current batch",
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for("loadingMsg.hidden && candidates().length === 5", "deferred rescan")
    cleanup.check(
        page,
        "JSON.stringify(batchKeys()) === JSON.stringify(nextExpected) && "
        "ordinary().some(c=>cleanupKey(c)===unchecked)",
        "deferral survives refresh",
    )
    page.evaluate(
        "window.dragged=candidates()[0]; const dt=new DataTransfer(); "
        "dragged.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:dt})); "
        "colTrash.dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:dt})); "
        "dragged.dispatchEvent(new DragEvent('dragend',{bubbles:true,dataTransfer:dt}));"
    )
    cleanup.check(
        page,
        "candidates().length === 0 && !cleanupGroup.hidden && !cleanupNext.disabled && "
        "!cleanupEmpty.hidden && cleanupSelectAll.disabled && cleanupQueue.disabled && "
        "cleanupHeading.textContent === 'Cleanup suggestions · 0 shown · 7 more'",
        "scoped drag completes batch and preserves context and next button",
    )
    page.evaluate("performUndo()")
    cleanup.check(
        page,
        "candidates().length === 1 && nextExpected.includes(batchKeys()[0]) && "
        "cleanupHeading.textContent.endsWith('7 more')",
        "completed-batch undo restores without advancing",
    )

    reset_page(page, base_url)
    page.evaluate("window.visited=[]; window.counts=[]")
    for expected in [5, 5, 5, 2]:
        cleanup.check(
            page, f"candidates().length === {expected}", f"sequential batch contains {expected}"
        )
        if expected == 2:
            snapshots.append(snapshot(page, "final-two"))
        page.evaluate(
            "counts.push(candidates().length); visited.push(...batchKeys()); "
            "click('#cleanup-queue')"
        )
        if expected != 2:
            cleanup.check(
                page,
                "!cleanupGroup.hidden && !cleanupNext.disabled && candidates().length === 0",
                "completed batch offers explicit next without Done",
            )
            if page.evaluate("counts.length === 1"):
                snapshots.append(snapshot(page, "batch-completed"))
            page.evaluate("click('#cleanup-next')")
    cleanup.check(
        page,
        "new Set(visited).size === 17 && visited.length === 17 && "
        "cleanupGroup.hidden && cardsTrash.querySelectorAll('.card').length === 17",
        "5 → 5 → 5 → 2 reviews each candidate exactly once and hides exhausted section",
    )
    page.evaluate("performUndo()")
    cleanup.check(
        page,
        "!cleanupGroup.hidden && candidates().length === 1 && cleanupNext.disabled",
        "undo after exhaustion restores the final batch",
    )

    reset_page(page, base_url)
    # Move the tracked duplicate's batch into view explicitly, then rename it.
    page.evaluate(
        "window.tracked=[...document.querySelectorAll('.card')].find(c=>"
        "c.dataset.source!=='Desktop' && c.dataset.filename === "
        "'Screenshot 2026-02-16 at 19.58.20.png'); "
        "while(!cleanupCards.contains(tracked) && !cleanupNext.disabled) click('#cleanup-next'); "
        "tracked.querySelector('.cleanup-select').click(); "
        "openRenameModal(tracked); renameInput.value='Screenshot batch-reference.png'; "
        "renameConfirm.click()"
    )
    page.wait_for(
        "tracked.dataset.filename === 'Screenshot batch-reference.png'", "batch fixture rename"
    )
    page.evaluate("window.renameBatch=batchKeys(); refreshScreenshots()")
    page.wait_for(
        "loadingMsg.hidden && batchKeys().includes('"
        + str(ROOT / demo_fixtures.TRACKED_DIR)
        + "|Screenshot batch-reference.png')",
        "renamed batch rescan",
    )
    cleanup.check(
        page,
        "JSON.stringify(batchKeys()) === JSON.stringify(renameBatch) && "
        "candidates().some(c=>c.dataset.filename === 'Screenshot batch-reference.png' && "
        "!c.querySelector('.cleanup-select').checked)",
        "rename preserves slots and unchecked choices on refresh",
    )
    page.evaluate(
        "window.beforeMissing=batchKeys(); fetch('/__test/disappear',{method:'POST'})",
        await_promise=True,
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "loadingMsg.hidden && document.querySelectorAll('.card').length === 20",
        "missing file rescan",
    )
    cleanup.check(
        page,
        "candidates().length === beforeMissing.length-1 && "
        "batchKeys().every(k=>beforeMissing.includes(k))",
        "missing file is removed without filling its slot",
    )
    page.evaluate(
        "window.original=[...document.querySelectorAll('.card')].find(c=>"
        "c.dataset.source==='Desktop' && "
        "c.dataset.filename === 'Screenshot 2026-02-16 at 19.58.20.png'); "
        "while(!cleanupCards.contains(original) && !cleanupNext.disabled) click('#cleanup-next'); "
        "window.beforeStale=batchKeys(); fetch('/__test/later-open',{method:'POST'})",
        await_promise=True,
    )
    page.evaluate("refreshScreenshots()")
    page.wait_for(
        "loadingMsg.hidden && !cleanupCandidates().some(c=>c.dataset.filename === "
        "'Screenshot 2026-02-16 at 19.58.20.png')",
        "stale metadata rescan",
    )
    cleanup.check(
        page,
        "!candidates().some(c=>c.dataset.filename === 'Screenshot 2026-02-16 at 19.58.20.png') && "
        "batchKeys().every(k=>beforeStale.includes(k))",
        "fresh metadata removes stale activity without advancing",
    )
    if page.exceptions:
        raise baseline.CaptureError(f"Browser script errors: {page.exceptions}")
    return snapshots


def main() -> int:
    chrome = baseline.find_chrome()
    if not chrome:
        raise baseline.CaptureError("Chrome is required for cleanup batch UI verification")
    manifest = demo_fixtures.write_workspace(ROOT, force=True)
    original = ROOT / demo_fixtures.DESKTOP_DIR / demo_fixtures.CATALOGUE[5].name
    (ROOT / demo_fixtures.TRACKED_DIR / original.name).write_bytes(original.read_bytes())
    state = ROOT / demo_fixtures.RUNTIME_DIR / demo_fixtures.STATE_DIR / "state.json"
    state.write_text(json.dumps({"decisions": {}}) + "\n")
    OUT.mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        server = stack.enter_context(baseline.AppServer(ROOT, bootstrap=BOOTSTRAP))
        profile = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="ss-dcl-batches-chrome-"))
        )
        browser = stack.enter_context(baseline.ChromeSession(chrome, profile))
        page = browser.new_page()
        stack.callback(page.close)
        page.call("Page.enable")
        page.call("Runtime.enable")
        shots = cleanup.capture_matrix(page, server.base_url, OUT)
        for theme in ["light", "dark"]:
            injected = page.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": baseline._theme_source(theme),
                },
            )
            for width, height in [(1440, 900), (320, 900)]:
                shots.append(
                    baseline.capture(
                        page,
                        base_url=server.base_url,
                        viewport=baseline.Viewport(f"{width}x{height}", width, height, "batch"),
                        state=baseline.CaptureState(
                            "scrolled", "Persistent review context", prepare=scroll_context
                        ),
                        out_dir=OUT,
                        theme=theme,
                        scale=1,
                        settle=0.2,
                        timeout=15,
                    )
                )
            page.call(
                "Page.removeScriptToEvaluateOnNewDocument", {"identifier": injected["identifier"]}
            )
        snapshots = interactions(page, server.base_url)
        (OUT / "verification.json").write_text(
            json.dumps(
                {
                    "browser": browser.version(),
                    "seed": manifest["seed"],
                    "fixed_scan_time": cleanup.NOW.isoformat(),
                    "eligible": 17,
                    "batch_sequence": [5, 5, 5, 2],
                    "screenshots": [shot.path.name for shot in shots] + snapshots,
                    "interaction_checks": "passed",
                },
                indent=2,
            )
            + "\n"
        )
    print(f"All cleanup batch UI checks passed; screenshots: {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except baseline.CaptureError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
