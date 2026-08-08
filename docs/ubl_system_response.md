# UBL Document Scan System Response

This document explains how the current `Document_Scan` system addresses the proposal review points, and where the implementation already supports or should extend controls for banking-grade deployment.

## 1. Scope and Customer Clarification
- The repo implements a banking document verification platform targeted at branch scanning and account opening workflows.
- The system architecture and APIs reference UBL-style verification flows in `app/services/verification_service.py`, `app/services/verification_pipeline.py`, and `app/routes/verification.py`.
- Any customer relationship wording should be unified to UBL in the final proposal, with TPS referenced only if it is the contracting or delivery partner.

## 2. Performance and Quality Measurement
### Current Implementation
- OCR extraction is performed by `app/services/ocr_service.py` and `app/services/extraction_service.py`.
- Signature comparison uses `app/services/signature_compare.py` and local Siamese model weights from `app/services/signature_siamese.py`.
- Quality checks are implemented in `app/services/image_quality.py`.

### What the system can support
- Document-level accuracy metrics: field extraction completeness, missing-value rate, and schema validation pass rate.
- Signature similarity metrics: `match_percentage` from `compare_signature_bytes()` and a configurable threshold in `app/config.py` via `SIGNATURE_MATCH_THRESHOLD`.
- Fraud signal metrics: metadata integrity flags, editing-software detection, and document gate classification confidence.
- Performance metrics: request latency per API, throughput by concurrent branch scan jobs, and report generation time.

### Recommended KPI definitions
- OCR accuracy: percentage of required fields extracted correctly by document type.
- Signature verification: match / no-match at threshold 95%, with measured FAR/FRR from a validation set.
- False-positive risk: count of metadata integrity or tampering flags requiring manual review.
- Availability: service uptime for FastAPI backend and email verification workers.

## 3. Signature Model Evidence and Validation
### Current system behavior
- The repository uses a Siamese CNN signature encoder in `app/services/signature_siamese.py`.
- `app/services/signature_compare.py` attempts local Siamese comparison first; if unavailable, it falls back to Gemini Vision comparison.
- The local model can be trained via `scripts/train_signature_siamese.py`.

### Evidence available in code
- Match results are produced as a percentage and auxiliary scores (`visual_similarity`, `similarity`) in `compare_siamese_bytes()`.
- A default threshold is defined in `app/config.py`: `SIGNATURE_MATCH_THRESHOLD = 95.0`.

### Missing or recommended validation artifacts
- Dataset composition and provenance are not present in the repo; the training script currently generates synthetic stroke pairs rather than a labelled real-world signature corpus.
- Threshold selection methodology is currently configurable but not documented as a statistical process.
- Independent test and validation results should be captured in a separate evaluation report or dataset release.
- Recommended additions:
  - a labeled UBL signature verification dataset,
  - a held-out test set for FAR/FRR computations,
  - a threshold selection plan with ROC analysis,
  - periodic revalidation for model drift.

## 4. Fraud-Detection Explanation and Metadata Signals
### Current implementation
- `app/services/image_quality.py` inspects image metadata and file headers for editing software markers such as Canva, Photoshop, GIMP, Figma, and others.
- `app/routes/branch.py` exposes this as `flags` and `editing_detected` in the branch scan API.
- The check currently returns a tampering flag on metadata detection.

### Risk signal handling
- Metadata traces are a risk indicator, not definitive proof of forgery.
- In a production banking workflow, this should feed into a review decision rather than become conclusive evidence.
- The existing repo can support this as:
  - `metadata_integrity` check in `ImageQualityService`,
  - a separate audit flag for manual review,
  - combination with OCR/validation mismatches and document-type classifier confidence.

### Recommended stance
- Treat software metadata as a risk signal that raises the case to review.
- Corroborate with additional evidence: document gate rejection, OCR mismatches, missing fields, validation failures, and signature comparison anomalies.

## 5. LLM Controls and Governance
### Existing LLM controls
- Prompt enforcement is centralized via `app/prompts/common.py`:
  - JSON-only output,
  - no markdown fences,
  - null for missing fields,
  - explicit no-hallucination instruction.
- Provider abstraction is implemented in `app/services/llm_factory.py` for Gemini, Groq, and Ollama.
- `GeminiService` and `OllamaService` both retry failed structured extraction results and validate JSON with `app/services/schema_parser.py`.
- `ExtractionPipeline` uses `temperature = 0.0` and deterministic prompt construction.
- Post-processing corrections for deterministic values are performed in `ExtractionPipeline._post_correct_fields()`.

### Where control is already enforced
- Output validation against Pydantic schemas.
- Retry-on-failure strategy with increasingly explicit prompt reminders.
- Separate branch vs account-application API key handling via `resolve_gemini_api_key()`.
- Optional local model hosting via Ollama and cloud hosting via Gemini/Groq.

### Recommended controls to strengthen governance
- Confidence scoring for every LLM extraction result.
- Explicit hallucination logging and mismatch audit trail.
- Prompt security review and a prompt registry lifecycle in `PromptManager`.
- Deterministic validation workflows for high-risk fields.
- Human-in-the-loop review for uncertain or low-confidence outputs.
- Model hosting policy: cloud vs on-prem semantics, version locking, and fallback behavior.

## 6. Architecture and Deployment
### System architecture today
- FastAPI backend (`app/main.py`, `app/routes/*`).
- Document upload and storage in `UPLOAD_DIR` with relative paths in metadata records.
- Relational metadata in `DATABASE_URL`, configured for PostgreSQL in `app/config.py`.
- OCR, LLM extraction, signature compare, validation, and report generation are modular service layers.

### Deployment options
- Cloud/hybrid deployment:
  - PostgreSQL production database,
  - cloud LLM provider (Gemini or Groq),
  - optional local Ollama for branch-side processing,
  - object store for file attachments.
- On-prem deployment:
  - local database and file storage,
  - Ollama local LLM hosting,
  - internal networking for branch devices.

### Clarifying database intent
- The repo is designed for PostgreSQL as the production database.
- SQLite is only a likely development/test fallback and should not be treated as a production bank database.

### Data flow summary
1. User uploads document via API route or branch scan.
2. File is saved under `UPLOAD_DIR` and linked from metadata.
3. `ImageQualityService` assesses image integrity and metadata.
4. `ExtractionPipeline` performs OCR and LLM-based field extraction.
5. Validation engine checks extracted fields against business rules.
6. Signature comparison occurs via `signature_compare.py`.
7. Verification email workflow optionally sends a company email and tracks the reply.

### Integration points
- Document intake APIs in `app/routes/applications.py`, `app/routes/branch.py`, `app/routes/verification.py`.
- Signature registration and comparison in `app/routes/signatures.py`.
- Verification workflow in `app/services/verification_service.py` and `app/services/verification_pipeline.py`.
- Audit logging in `app/services/audit.py` and `app/models.py`.

## 7. Security, Compliance, and Operational Controls
### Implementation evidence
- Audit log storage via `app/models.py` and `app/services/audit.py`.
- Email verification target validation in `app/services/email_service.py`.
- Reply validation in `app/verification_reply_worker.py`.
- Session secrets and environment-based config in `app/config.py`.
- File validation by extension and size in several upload routes.

### Controls that should be documented or added
- Data residency and retention policies.
- Encryption at rest for uploaded documents and database fields.
- Encryption key management and KMS integration.
- Privileged access controls for operators and administrators.
- Penetration testing scope and periodic security review.
- Audit retention and log archival.
- Regulatory mapping to banking compliance standards.

## 8. Email Verification Risk Controls
### Existing protections
- Company email targets are validated with `validate_verification_target()` in `app/services/email_service.py`.
- Free email domains are rejected.
- MX host resolution and SMTP recipient verification are attempted.
- The email body contains strict response instructions.
- Inbound replies are checked in `app/verification_reply_worker.py` against the original `company_email`.

### Risk management
- The current system already treats email verification as a controlled corporate-domain workflow, not a free-mail flow.
- It prevents open reply acceptance by only processing replies from the intended company address.

### Recommended enhancements
- Explicit official-domain validation and corporate email allowlisting.
- Secure transmission of documents via encrypted links or portal access instead of raw attachments where possible.
- Recipient authentication and one-time verification tokens for recipient identity.
- Clear consent logging for each verification email.

## 9. Implementation Plan and Acceptance Criteria
### Suggested phased delivery
- Phase 1: Branch document intake, OCR extraction, and quality checks.
- Phase 2: Document classification and structured extraction for CNIC, payslip, and bank statement.
- Phase 3: Signature verification integration and threshold-based match reporting.
- Phase 4: Company email verification and reply processing.
- Phase 5: Production hardening: security, DR, performance, and audit compliance.

### Key milestones
- Functional branch scan API and document gate.
- Verified extraction for target document types.
- Signature compare pass/fail with review flag.
- Secure email verification workflow completed.
- Audit and logging for all high-risk decisions.

### Acceptance criteria
- Extraction accuracy and field completeness measured against test cases.
- Signature comparison returns consistent match scores and falls back gracefully.
- Metadata risk signals do not cause unwarranted rejection without review.
- Email verification is accepted only from the intended corporate sender.
- Audit logs capture every verification, decision, and email event.

## 10. Commercial and Infrastructure Notes
- The current codebase contains no pricing or warranty information; those belong in the commercial proposal.
- Recommended commercial assumptions:
  - PostgreSQL database hosting,
  - secure object storage for uploads,
  - LLM API costs for Gemini/Groq or compute costs for Ollama,
  - maintenance and SaaS support fees,
  - service-level agreements for uptime, response time, and issue resolution.

## 11. Terminology and Workflow Clarification
- Correct the terminology "Custom Tainted Models" to "custom trained models" or "custom AI models."
- The solution is composed of more than three workflows:
  - document intake,
  - document gate / classification,
  - OCR + LLM extraction,
  - signature verification,
  - company verification email/reply.
- The proposal should reflect the actual workflow count and the interdependencies between them.

## 12. Direct Responses to the Review Points
This section provides a clear, professional response to each of the review points raised.

- No measurable performance commitments: The current system can support defined performance targets, including OCR accuracy, forgery detection precision, false-positive rates, signature FAR/FRR, response time, throughput, and availability. These can be added as formal metrics and tracked through testing and operational monitoring.

- Insufficient model evidence: The repository includes a signature verification model and code, but it does not include an audited dataset description or independent validation report. We recommend documenting dataset composition, test methodology, and threshold-selection criteria before presenting claims about training volume and customer suitability.

- Weak fraud-detection explanation: The system treats file metadata signals as indicators rather than absolute proof. Metadata such as Canva or Photoshop tags is used as a risk factor that triggers further review, not as sole evidence of forgery.

- LLM controls are unspecified: The implementation already includes deterministic prompt templates, strict JSON validation, and retry logic for structured output. To complete the proposal, the document should also describe hallucination prevention, confidence scoring, prompt security, human review, and model hosting options.

- Architecture is missing: The product can be deployed on-premises, in the cloud, or in a hybrid model. The architecture should define data flow, network boundaries, integration points, storage architecture, scalability, and disaster recovery strategy.

- Security and compliance lack detail: The system currently supports audit logging and target validation, but the proposal should explicitly cover data residency, retention, deletion, encryption and key management, privileged access, model governance, consent, penetration testing, audit retention, and applicable banking regulations.

- Email verification creates risk: The current design restricts verification to corporate email addresses and validates replies against the intended recipient address. This should be documented as a controlled, authenticated workflow with secure delivery and consent handling.

- No implementation plan: The final proposal should include milestones, delivery schedule, pilot plan, migration approach, training, support model, staffing responsibilities, and acceptance criteria.

- No commercial information: Pricing, licensing, infrastructure costs, maintenance, warranties, and service-level agreements are business topics for the commercial section, not the technical design section.

- Technology ambiguity: PostgreSQL is the correct production database choice for a banking-scale deployment, while SQLite is only a development or test convenience. The proposal should be explicit about production database selection.

- Terminology issue: The phrase "Custom Tainted Models" appears to be a wording error. It should be corrected to "custom trained models."

- Client identity inconsistency: The proposal should clarify whether the client is UBL, TPS, or both, and make the relationships explicit.

- Workflow inconsistency: Company verification is a distinct workflow and should be described separately from the core document ingestion and analysis workflows.

## 13. Repository Alignment Summary
- `app/services/image_quality.py` and `app/routes/branch.py` implement metadata risk detection.
- `app/services/signature_compare.py` and `app/services/signature_siamese.py` implement signature verification with local and cloud fallback.
- `app/prompts/common.py`, `app/services/llm_factory.py`, `app/services/gemini_service.py`, and `app/services/ollama_service.py` implement deterministic LLM prompt controls and validation.
- `app/services/verification_service.py` and `app/services/verification_pipeline.py` implement verification workflow and review tracking.
- `app/services/email_service.py` and `app/verification_reply_worker.py` implement company email validation and reply verification.
- `app/models.py` and `app/services/audit.py` support auditability.

---

This document is intended as a technical response to the review comments, showing how the system currently addresses the concerns and where the proposal should be strengthened for a banking-scale deployment.