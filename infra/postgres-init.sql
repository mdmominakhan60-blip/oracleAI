-- The pgvector image provides this extension; the application role owns the
-- database and can use vector columns created by Alembic/runtime bootstrap.
CREATE EXTENSION IF NOT EXISTS vector;
