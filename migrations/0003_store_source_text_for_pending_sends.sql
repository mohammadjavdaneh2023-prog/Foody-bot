ALTER TABLE outbound_jobs
    ADD COLUMN source_text TEXT NOT NULL DEFAULT '';
