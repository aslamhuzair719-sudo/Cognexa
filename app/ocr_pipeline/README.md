# UBL Remittance OCR Pipeline

Production ROI-based OCR for phone-captured UBL Application / Remittance forms.

## Pipeline

```
Input Image
  → Detect Document
  → Perspective Correction
  → Deskew
  → Resize to Fixed Template Size   ← locks percentage ROIs
  → CLAHE / Denoise / Sharpen / Adaptive Threshold / Line Removal
  → Generate Normalized ROIs
  → Save ROI Overlay + per-field crops
  → PaddleOCR on EACH ROI (never full page)
  → Checkbox ink → true/false
  → Post-process → Validate → JSON
```

## Why ROIs were wrong before

Warped pages had variable pixel sizes after perspective correction, and the
ROI map was calibrated for a different slip layout. This pipeline:

1. Resizes every page to `template_size` from the JSON (default 1000×1400)
2. Stores every box as page fractions `[x, y, w, h]` in `[0, 1]`
3. Rejects absolute pixel boxes in the template
4. Crops with zero padding / optional `label_inset` so labels stay out

## Calibrating ROIs

Edit **only** `templates/ubl_remittance_rois.json` — no OCR code changes needed.

1. Run with `--debug`
2. Open `uploads/ocr_debug/roi_overlay.png`
3. Adjust normalized boxes until each colored rectangle covers **only the value**
4. Check per-field crops: `uploads/ocr_debug/applicant_name.png`, etc.
5. Low-confidence crops land in `uploads/ocr_debug/low_confidence/`

## Debug outputs

| Path | Content |
|------|---------|
| `roi_overlay.png` | Multi-color ROI overlay |
| `{field}.png` | Individual ROI crop |
| `low_confidence/{field}.png` | Conf < 0.75 |
| `01_warped_color.png` | Template-sized color page |
| `02_ocr_ready.png` | Binary OCR canvas |

## API

```
POST /api/v1/ocr/remittance
```

Customer-submitted remittance forms use this Python ROI + PaddleOCR pipeline.

Branch officer scans (`POST /api/v1/branch/scan-document` with
`document_type=remittance_slip`) use **LLM vision extraction** instead
(`app.ocr_pipeline.llm_extract.extract_remittance_with_llm`).

## CLI

```bash
python scripts/run_remittance_ocr.py path/to/form.jpg --debug --fields-only
```

## Config (env)

- `OCR_SAVE_DEBUG=1`
- `OCR_DETECT_DOCUMENT=1`
- `OCR_REMOVE_TABLE_LINES=1`
- `PADDLE_OCR_LANG=en`
- `PADDLE_USE_ANGLE_CLS=1`
