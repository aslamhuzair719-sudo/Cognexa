#!/usr/bin/env python
"""CLI: run remittance OCR on a local image file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root on path when run as script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr_pipeline import RemittanceOCRPipeline
from app.ocr_pipeline.config import PipelineConfig
from app.ocr_pipeline.pipeline import EMPTY_CHECKBOXES, EMPTY_FIELDS


def main() -> int:
    parser = argparse.ArgumentParser(description="UBL remittance form OCR")
    parser.add_argument("image", type=Path, help="Path to remittance form image")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save preprocess / ROI debug images under uploads/ocr_debug",
    )
    parser.add_argument(
        "--roi-template",
        type=Path,
        default=None,
        help="Override ROI JSON template path",
    )
    parser.add_argument(
        "--fields-only",
        action="store_true",
        help="Print only the canonical field JSON (no meta/validation)",
    )
    args = parser.parse_args()

    if not args.image.exists():
        print(f"File not found: {args.image}", file=sys.stderr)
        return 1

    cfg = PipelineConfig.default()
    if args.debug:
        cfg.save_debug_images = True
    if args.roi_template:
        cfg.roi_template_path = args.roi_template

    result = RemittanceOCRPipeline(config=cfg).process(
        args.image, include_debug=args.debug
    )

    if args.fields_only:
        out = {k: result.get(k, "") for k in EMPTY_FIELDS}
        checkboxes = {k: bool(result.get(k, False)) for k in EMPTY_CHECKBOXES}
        out.update(checkboxes)
        out["checkboxes"] = checkboxes
    else:
        out = result

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
