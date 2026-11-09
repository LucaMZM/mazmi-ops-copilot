-- 005: MAZMI 2.0 reliability. Additive only: no drops, renames or type changes.
-- Conversations: recency ordering, rename and archive (soft delete keeps audit links).
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS updated_at timestamptz;
UPDATE conversations c
   SET updated_at = coalesce(
     (SELECT max(m.created_at) FROM messages m WHERE m.conversation_id = c.id), c.created_at)
 WHERE c.updated_at IS NULL;
ALTER TABLE conversations ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE conversations ALTER COLUMN updated_at SET NOT NULL;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS archived_at timestamptz;
CREATE INDEX IF NOT EXISTS conversations_recent_idx
  ON conversations(workspace_id, updated_at DESC) WHERE archived_at IS NULL;

-- Structured chunking keeps the heading path of each chunk as metadata. Existing
-- chunks remain valid with NULL; content, vectors and collections are untouched.
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS section text;

-- Chat idempotency: one stored outcome per (user, client request id). A retried or
-- duplicated request replays the committed turn instead of creating a second
-- proposal. Rows are short-lived and pruned by the application after 24 hours.
CREATE TABLE IF NOT EXISTS chat_requests (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_id uuid NOT NULL,
  workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, request_id)
);
CREATE INDEX IF NOT EXISTS chat_requests_created_idx ON chat_requests(created_at);
