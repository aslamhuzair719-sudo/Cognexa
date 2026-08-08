# Technical Proposal – Document Scan & Verification System

## 1. Overall Objective
Build an intelligent document processing system that can:
- accept scanned or photographed documents,
- detect whether the uploaded image is a valid document,
- classify the document type,
- extract structured information using OCR,
- validate the extracted data,
- compare signatures using AI,
- and generate a final verification report.

---

## 2. Module-wise Technical Proposal

| Module | Purpose | Proposed Technical Approach | Expected Output |
|---|---|---|---|
| Document Intake | Receive uploaded images and store them safely | REST API, file validation, metadata handling, UUID-based storage | Secure document record |
| Document Detection Gate | Check whether the image contains a real document and whether it is supported | Vision-based classifier / LLM-based gate | document status, type, confidence |
| Image Quality Assessment | Reject poor-quality scans before extraction | OpenCV-based quality checks: blur, contrast, skew, glare, resolution | quality score and pass/fail |
| OCR Extraction Engine | Extract text fields from documents | ROI-based OCR pipeline + PaddleOCR, with LLM fallback for complex cases | structured JSON data |
| Signature Scan | Verify whether a signature matches the registered one | Siamese network with embedding similarity | match percentage, confidence |
| Validation Engine | Validate extracted content against business rules | Rule-based validation + consistency checks | validation report |
| Document Routing | Route each document to the right extraction logic | Type-based workflow engine | correct processing pipeline |
| Reporting & Audit | Generate final report and maintain logs | Report generator + audit storage | PDF/JSON report and audit record |

---

## 3. Detailed Module Design

### A. Document Intake Module
- Accepts image uploads from frontend or API.
- Validates file type, size, and format.
- Stores the original image and processed copies.
- Maintains metadata such as document type, timestamp, branch, and user ID.

Technical stack:
- Python / FastAPI
- File storage: local directory or cloud storage
- Database: PostgreSQL / SQLite for metadata

Output:
- upload_id
- original file path
- metadata record

### B. Document Detection Gate
This module acts as the first decision layer.

Responsibilities:
- Determine whether the image is a document or just a random photo.
- Identify the document category such as CNIC, Payslip, or Remittance.
- Score confidence for the decision.

Proposed approach:
- Stage 1: document presence detection
- Stage 2: supported document type detection

Model / technique:
- Vision-based classification
- LLM-assisted detection for ambiguous cases

Output:
- is_document: true/false
- detected_type
- confidence score
- reason for rejection or acceptance

### C. Image Quality Assessment Module
Before OCR, the system should check whether the document is scan-worthy.

Checks include:
- blur detection
- low contrast
- skew / rotation
- glare / shadow
- insufficient resolution
- cropped or incomplete page

Proposed approach:
- OpenCV-based preprocessing
- Rule-based scoring

Output:
- quality_score
- quality_status: pass / fail / review
- recommended correction

### D. OCR Extraction Module
This is the main information extraction engine.

Responsibilities:
- detect the document layout,
- locate relevant fields,
- perform OCR,
- map values into structured fields.

Proposed approach:
- ROI-based OCR pipeline for stable forms
- Template-based region extraction
- PaddleOCR for text recognition
- LLM vision model as fallback when layout is complex or uncertain

Output:
- extracted fields such as:
  - applicant_name
  - father_name
  - account_number
  - amount
  - document_date
  - reference_number

### E. Signature Scan Module
This module verifies whether the uploaded signature matches the registered signature.

Proposed model:
- Siamese neural network

Why Siamese network:
- It learns a similarity function rather than only a class label.
- It is well-suited for one-to-one verification tasks.

Workflow:
1. Preprocess signature image
2. Convert to grayscale
3. Normalize size and contrast
4. Generate embedding vector
5. Compare embeddings using cosine similarity or Euclidean distance

Technical approach:
- CNN-based Siamese encoder
- embedding dimension: 128
- similarity score in percentage

Output:
- match_percentage
- similarity_score
- verification_status: match / no_match / review

### F. Validation Engine
This module checks whether the extracted data is logically correct.

Validation rules can include:
- required fields missing
- format validation
- numeric range checks
- inconsistent date values
- mismatch between extracted fields and known patterns

Proposed approach:
- rule-based validation engine
- optional ML-based anomaly detection

Output:
- valid / invalid / needs_review
- list of issues
- confidence score

### G. Document Routing Module
Different documents require different extraction prompts and validation logic.

Examples:
- CNIC → identity fields
- Payslip → salary, employer, month
- Remittance → amount, reference, beneficiary details

Proposed approach:
- Document type-based routing
- Prompt / template selection engine

Output:
- selected extraction strategy
- selected validation rules

### H. Reporting & Audit Module
The system should produce a human-readable final report.

Contents:
- document summary
- extracted fields
- OCR confidence
- signature verification result
- validation issues
- audit metadata

Output:
- JSON result
- PDF/HTML report
- audit log entry

---

## 4. Recommended Tech Stack

- Backend: Python, FastAPI
- OCR: PaddleOCR
- AI Vision: LLM-based extraction
- Signature Verification: PyTorch, Siamese CNN
- Image Processing: OpenCV
- Database: PostgreSQL / SQLite
- Frontend: React + Vite
- Storage: local filesystem or cloud object storage

---

## 5. Suggested Implementation Phases

1. Phase 1: Upload + storage + document detection
2. Phase 2: Image quality assessment + OCR extraction
3. Phase 3: Signature verification
4. Phase 4: Validation engine + reporting
5. Phase 5: UI integration and production hardening

---

## 6. Summary
The system can be designed as a multi-stage AI pipeline:

- Intake
- Detection
- Quality Check
- OCR
- Signature Verification
- Validation
- Report Generation

This architecture is scalable, modular, and suitable for production deployment.
