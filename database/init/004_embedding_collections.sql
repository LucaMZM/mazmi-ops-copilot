-- Preserve existing OpenAI vectors, allow differently sized vectors in isolated collections.
DROP INDEX IF EXISTS chunks_embedding_hnsw;
ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dimensions integer NOT NULL DEFAULT 1536;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_collection text;
UPDATE documents SET embedding_collection='openai:' || coalesce(embedding_model,'unknown') || ':1536:legacy'
 WHERE embedding_collection IS NULL;
ALTER TABLE documents ALTER COLUMN embedding_collection SET NOT NULL;
ALTER TABLE documents ALTER COLUMN embedding_collection SET DEFAULT 'openai:text-embedding-3-small:1536:legacy';
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_collection text;
UPDATE document_chunks c SET embedding_collection=d.embedding_collection FROM documents d
 WHERE c.document_id=d.id AND c.embedding_collection IS NULL;
ALTER TABLE document_chunks ALTER COLUMN embedding_collection SET NOT NULL;
CREATE INDEX IF NOT EXISTS chunks_collection_idx ON document_chunks(workspace_id,embedding_collection);
CREATE OR REPLACE FUNCTION validate_chunk_collection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE dimensions integer; collection text; workspace uuid;
BEGIN
 SELECT embedding_dimensions,embedding_collection,workspace_id INTO dimensions,collection,workspace
 FROM documents WHERE id=NEW.document_id FOR SHARE;
 IF NOT FOUND OR vector_dims(NEW.embedding) != dimensions OR workspace != NEW.workspace_id THEN
  RAISE EXCEPTION 'Invalid chunk dimensions or workspace';
 END IF;
 IF NEW.embedding_collection IS NOT NULL AND NEW.embedding_collection != collection THEN
  RAISE EXCEPTION 'Invalid embedding collection';
 END IF;
 NEW.embedding_collection=collection;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS chunk_collection_guard ON document_chunks;
CREATE TRIGGER chunk_collection_guard BEFORE INSERT OR UPDATE ON document_chunks
 FOR EACH ROW EXECUTE FUNCTION validate_chunk_collection();
CREATE OR REPLACE FUNCTION validate_document_collection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS (SELECT 1 FROM document_chunks WHERE document_id=NEW.id
  AND (embedding_collection != NEW.embedding_collection OR vector_dims(embedding) != NEW.embedding_dimensions
       OR workspace_id != NEW.workspace_id)) THEN
  RAISE EXCEPTION 'Document collection changed without reindexing chunks';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS document_collection_guard ON documents;
CREATE CONSTRAINT TRIGGER document_collection_guard AFTER UPDATE ON documents
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_document_collection();
