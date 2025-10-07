CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    snapshot JSONB,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crdt_ops (
    op_id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(doc_id),
    type TEXT,
    char TEXT,
    after_id TEXT,
    client_id TEXT,
    created_at TIMESTAMP DEFAULT now()
);
