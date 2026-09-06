-- The pgvector image provides this extension; the application role owns the
-- database and can use vector columns created by Alembic/runtime bootstrap.
CREATE EXTENSION IF NOT EXISTS vector;

-- The oracle_test role (least-privilege for agent test runs, BUS-303) is
-- provisioned by the docker-entrypoint shell script mounted below.
-- For existing clusters (restores, migrated volumes) use `make ensure-test-role`.
