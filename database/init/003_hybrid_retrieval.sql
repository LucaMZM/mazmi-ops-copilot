-- Generated column backfills existing chunks; no embedding regeneration required.
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('spanish'::regconfig, content)) STORED;
CREATE INDEX IF NOT EXISTS chunks_search_gin ON document_chunks USING gin(search_vector);
