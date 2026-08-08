import os
from app import config
from app.db import SessionLocal
from app.models import BranchEntry
from app.services.verification_service import create_branch_entry_verification
from uuid import UUID

entry_id = UUID('b0f00006-30a9-4a26-8e6f-63f5b6af967e')

with SessionLocal() as db:
    entry = db.query(BranchEntry).filter(BranchEntry.id == entry_id).first()
    print('entry', bool(entry))
    if entry:
        print('branch_id', entry.branch_id)
        print('status', entry.verification_email_status)
        print('id', entry.verification_email_id)
        print('documents count', len(entry.documents or []))
        for doc in entry.documents or []:
            path = config.BRANCH_ENTRIES_DIR / doc.file_path
            print('doc', doc.id, doc.document_type, doc.file_path, path.exists())
        try:
            verification = create_branch_entry_verification(
                db,
                entry,
                document_type='payslip',
                target_email='test@company.com',
                note='test',
                user_id=1,
                username='admin',
            )
            print('verification created', verification.verification_id)
        except Exception as exc:
            import traceback
            traceback.print_exc()
