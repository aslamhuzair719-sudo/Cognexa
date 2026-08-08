from sqlalchemy import text
from app.db import engine

with engine.begin() as conn:
    result = conn.execute(text("SELECT 1 FROM information_schema.columns WHERE table_name='verifications' AND column_name='created_by'"))
    if result.first() is None:
        print('Adding created_by column to verifications')
        conn.execute(text('ALTER TABLE verifications ADD COLUMN created_by INTEGER REFERENCES users(id)'))
    else:
        print('created_by column already exists')
