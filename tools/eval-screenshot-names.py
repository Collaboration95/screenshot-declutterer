#!/usr/bin/env python3
"""LLM Screenshot Naming — Evaluation Framework.

Evaluates how well different LLM configurations generate short, filename-friendly
names for screenshots. Supports two pipelines:

    1.  OCR → text-only LLM    (pytesseract + Ollama text model)
    2.  Direct vision LLM       (Ollama vision model on raw image)

Outputs a structured JSON report for comparison across models, prompts,
and pipelines.

Usage:
    uv run python tools/eval-screenshot-names.py                # eval with defaults
    uv run python tools/eval-screenshot-names.py -n 10          # eval on 10 random screenshots
    uv run python tools/eval-screenshot-names.py -o report.json # custom output path
    uv run python tools/eval-screenshot-names.py --list-models  # show available models
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DESKTOP = Path.home() / "Desktop"
SCREENSHOT_GLOB = "Screenshot*.*"

# ── Standardised evaluation prompt ─────────────────────────────────────────
STANDARD_PROMPT = """You are renaming screenshot files. Given the text content found in a
screenshot, generate a short, descriptive filename (3-5 words).
Use lowercase, separate words with dashes.
Do NOT include the file extension in your answer — just the name part.

Example outputs:
- "customer-onboarding-discussion"
- "salary-delay-messages"
- "domain-selection-screen"
- "pr-review-comments"
- "dockerfile-build-error"

Screenshot text content:
---BEGIN SCREENSHOT TEXT---
{ocr_text}
---END SCREENSHOT TEXT---

Filename (3-5 words, lowercase, words separated by dashes):"""

VISION_STANDARD_PROMPT = (
    "Describe this screenshot in 3-5 words as a filename. "
    "Use lowercase, words separated by dashes. "
    "Only respond with the filename, nothing else."
)


# ── Data model ─────────────────────────────────────────────────────────────


@dataclass
class ScreenshotResult:
    """Per-screenshot evaluation result."""

    original_name: str
    size_bytes: int
    size_kb: float
    ocr_text: str
    ocr_text_length: int
    suggested_name: str
    word_count: int
    filename_safe: bool
    time_ms: float
    error: str | None = None


@dataclass
class ModelResult:
    """Aggregated result for one model/pipeline."""

    model_name: str
    model_size_gb: float
    approach: str  # "vision" | "ocr+text"
    prompt_used: str
    results: list[ScreenshotResult] = field(default_factory=list)
    avg_time_ms: float = 0.0
    avg_word_count: float = 0.0
    success_count: int = 0
    fail_count: int = 0

    def summarise(self) -> ModelResult:
        total = len(self.results)
        if total == 0:
            return self
        self.success_count = sum(1 for r in self.results if not r.error and r.suggested_name)
        self.fail_count = total - self.success_count
        if self.success_count > 0:
            successes = [r for r in self.results if r.suggested_name]
            self.avg_time_ms = sum(r.time_ms for r in successes) / len(successes)
            self.avg_word_count = sum(r.word_count for r in successes) / len(successes)
        return self


@dataclass
class EvalReport:
    """Top-level evaluation report."""

    generated_at: str
    eval_config: dict[str, Any]
    model_results: list[ModelResult] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────


def is_filename_safe(name: str) -> bool:
    """Check if *name* can be used as a filename (no path separators, no unsafe chars)."""
    if not name:
        return False
    # Must not contain path separators or control characters
    if re.search(r"[/\\:\0]", name):
        return False
    # Must be a reasonable length (2-200 chars)
    return 2 <= len(name) <= 200


def word_count(text: str) -> int:
    """Count words, treating dashes/hyphens as separators."""
    return len(re.findall(r"[a-zA-Z0-9]+", text.replace("-", " ")))


def clean_llm_output(raw: str) -> str:
    """Post-process LLM output to a clean filename stem (no extension)."""
    # Strip leading/trailing whitespace and quotes
    cleaned = raw.strip().strip('"').strip("'").strip("`")

    # If multiple lines, take the first non-empty line
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if lines:
        cleaned = lines[0]

    # Remove file extension if the model added one
    cleaned = re.sub(r"\.[a-zA-Z0-9]+$", "", cleaned)

    # Lowercase and replace spaces/underscores with dashes
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[_\s]+", "-", cleaned)

    # Remove any remaining unsafe filename characters
    cleaned = re.sub(r'[<>:"/\\|?*\']', "", cleaned)

    # Clean up multiple dashes
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-")

    return cleaned


# ── Pipelines ──────────────────────────────────────────────────────────────


def run_ocr(text_only: bool = True) -> str:
    """Extract text from screenshot using pytesseract."""
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(text_only)).strip()


def run_ocr_pipeline(screenshot_path: Path, model_name: str) -> ScreenshotResult:
    """Pipeline: OCR → text-only LLM."""
    import ollama
    import pytesseract
    from PIL import Image

    # 1. OCR
    ocr_text = pytesseract.image_to_string(Image.open(screenshot_path)).strip()

    # 2. Prompt construction
    prompt = STANDARD_PROMPT.format(ocr_text=ocr_text if ocr_text else "(no text detected)")

    # 3. LLM call
    t0 = time.perf_counter()
    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_name = response["message"]["content"]
        error = None
    except Exception as exc:
        raw_name = ""
        error = str(exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 4. Post-processing
    cleaned = clean_llm_output(raw_name) if not error else ""

    return ScreenshotResult(
        original_name=screenshot_path.name,
        size_bytes=screenshot_path.stat().st_size,
        size_kb=round(screenshot_path.stat().st_size / 1024, 1),
        ocr_text=ocr_text,
        ocr_text_length=len(ocr_text),
        suggested_name=cleaned,
        word_count=word_count(cleaned),
        filename_safe=is_filename_safe(cleaned),
        time_ms=round(elapsed_ms, 1),
        error=error,
    )


def run_vision_pipeline(screenshot_path: Path, model_name: str) -> ScreenshotResult:
    """Pipeline: direct vision LLM (image in, filename out)."""
    import ollama

    t0 = time.perf_counter()
    try:
        response = ollama.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": VISION_STANDARD_PROMPT,
                    "images": [str(screenshot_path)],
                }
            ],
        )
        raw_name = response["message"]["content"]
        error = None
    except Exception as exc:
        raw_name = ""
        error = str(exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    cleaned = clean_llm_output(raw_name) if not error else ""

    return ScreenshotResult(
        original_name=screenshot_path.name,
        size_bytes=screenshot_path.stat().st_size,
        size_kb=round(screenshot_path.stat().st_size / 1024, 1),
        ocr_text="",  # vision models don't use OCR
        ocr_text_length=0,
        suggested_name=cleaned,
        word_count=word_count(cleaned),
        filename_safe=is_filename_safe(cleaned),
        time_ms=round(elapsed_ms, 1),
        error=error,
    )


# ── Screenshot selection ───────────────────────────────────────────────────


def gather_screenshots(source_dir: Path, max_count: int | None = None) -> list[Path]:
    """Gather screenshot paths, optionally capped to *max_count* random ones."""
    paths = sorted(
        p
        for p in source_dir.glob(SCREENSHOT_GLOB)
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    if max_count and len(paths) > max_count:
        random.shuffle(paths)
        paths = paths[:max_count]
    return paths


# ── Main ───────────────────────────────────────────────────────────────────


def run_evaluation(
    screenshots: list[Path],
    models: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    """Run the full evaluation across all models and screenshots."""
    report = EvalReport(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        eval_config={
            "screenshot_count": len(screenshots),
            "model_count": len(models),
        },
    )

    for model_cfg in models:
        print(f"\n{'=' * 60}")
        print(f"Model: {model_cfg['name']}")
        print(f"Approach: {model_cfg['approach']}")
        print(f"Size: {model_cfg['size_gb']} GB")
        print(f"{'=' * 60}")

        pipeline = run_vision_pipeline if model_cfg["approach"] == "vision" else run_ocr_pipeline
        model_name = model_cfg["name"]

        model_result = ModelResult(
            model_name=model_name,
            model_size_gb=model_cfg["size_gb"],
            approach=model_cfg["approach"],
            prompt_used=(
                VISION_STANDARD_PROMPT if model_cfg["approach"] == "vision" else STANDARD_PROMPT
            ),
        )

        for i, ss_path in enumerate(screenshots, 1):
            print(f"  [{i}/{len(screenshots)}] {ss_path.name[:60]}...", end=" ")
            result = pipeline(ss_path, model_name)
            if result.error:
                print(f"FAILED: {result.error}")
            else:
                print(f'OK → "{result.suggested_name}" ({result.time_ms:.0f}ms)')
            model_result.results.append(result)

        model_result.summarise()
        report.model_results.append(model_result)

        print(
            f"  Summary: {model_result.success_count}/{len(screenshots)} OK, "
            f"avg {model_result.avg_time_ms:.0f}ms, "
            f"avg {model_result.avg_word_count:.1f} words"
        )

    # Serialise
    serialisable = asdict(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serialisable, indent=2, default=str))
    print(f"\nReport saved to {output_path}")
    return output_path


def print_model_list() -> None:
    """Print available models and their metadata for evaluation."""
    print(
        json.dumps(
            [
                # ── Text-only models (OCR pipeline) ──
                {
                    "name": "smollm:360m",
                    "size_gb": 0.7,
                    "approach": "ocr+text",
                    "params": "360M",
                    "notes": "Absolute smallest option. May struggle with quality.",
                },
                {
                    "name": "smollm:1.7b",
                    "size_gb": 1.5,
                    "approach": "ocr+text",
                    "params": "1.7B",
                    "notes": "Larger SmolLM variant, better quality.",
                },
                {
                    "name": "llama3.2:1b",
                    "size_gb": 1.0,
                    "approach": "ocr+text",
                    "params": "1B",
                    "notes": "Meta's smallest Llama 3.2.",
                },
                {
                    "name": "qwen2.5:1.5b",
                    "size_gb": 1.5,
                    "approach": "ocr+text",
                    "params": "1.5B",
                    "notes": "Alibaba Qwen, good multilingual support.",
                },
                {
                    "name": "gemma2:2b",
                    "size_gb": 1.5,
                    "approach": "ocr+text",
                    "params": "2B",
                    "notes": "Google's Gemma 2, strong at concise output.",
                },
                {
                    "name": "phi3:mini",
                    "size_gb": 2.5,
                    "approach": "ocr+text",
                    "params": "3.8B",
                    "notes": "Microsoft Phi-3, best text quality of small models.",
                },
                # ── Vision models (direct image) ──
                {
                    "name": "gemma4:e2b",
                    "size_gb": 7.7,
                    "approach": "vision",
                    "params": "5.1B total, ~2B active",
                    "notes": "Current vision baseline. Q4_K_M quant. Best quality so far.",
                },
            ],
            indent=2,
        )
    )


# ── CLI ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate LLM screenshot naming quality across models and pipelines.",
    )
    parser.add_argument(
        "-n",
        "--num-screenshots",
        type=int,
        default=10,
        help="Number of random screenshots to evaluate (default: 10)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("tools/eval-results/report.json"),
        help="Output JSON report path (default: tools/eval-results/report.json)",
    )
    parser.add_argument(
        "-m",
        "--model",
        action="append",
        dest="models",
        default=[],
        help="Model names to evaluate (can be repeated). Default: all available.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DESKTOP,
        help=f"Directory to scan for screenshots (default: {DESKTOP})",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print available model configurations and exit.",
    )
    args = parser.parse_args()

    if args.list_models:
        print_model_list()
        return

    # Gather screenshots
    screenshots = gather_screenshots(Path(args.source_dir), args.num_screenshots)
    if not screenshots:
        print(f"No screenshots found in {args.source_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(screenshots)} screenshots for evaluation")

    # Load model configs
    all_models = json.loads(
        """[
            {"name": "smollm", "size_gb": 0.7, "approach": "ocr+text"},
            {"name": "llama3.2:1b", "size_gb": 1.0, "approach": "ocr+text"},
            {"name": "qwen2.5:1.5b", "size_gb": 1.5, "approach": "ocr+text"},
            {"name": "gemma4:e2b", "size_gb": 7.7, "approach": "vision"}
        ]"""
    )
    if args.models:
        selected = [m for m in all_models if m["name"] in args.models]
        if not selected:
            print(f"No matching models for: {args.models}", file=sys.stderr)
            print("Available:", [m["name"] for m in all_models], file=sys.stderr)
            sys.exit(1)
        all_models = selected

    run_evaluation(screenshots, all_models, Path(args.output))


if __name__ == "__main__":
    main()
