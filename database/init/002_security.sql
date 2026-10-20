CREATE TABLE IF NOT EXISTS users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text UNIQUE NOT NULL,
 password_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS workspace_members (
 user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id,workspace_id)
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL DEFAULT now()+interval '1 day'
);
CREATE TABLE IF NOT EXISTS login_attempts (key text PRIMARY KEY, attempts integer NOT NULL, window_start timestamptz NOT NULL);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS indexed_at timestamptz;
ALTER TABLE pending_actions ADD COLUMN IF NOT EXISTS requested_by uuid REFERENCES users(id);
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id);
CREATE INDEX IF NOT EXISTS conversations_workspace_idx ON conversations(workspace_id);
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages(conversation_id,id);
CREATE INDEX IF NOT EXISTS audit_workspace_idx ON audit_events(workspace_id,created_at DESC);
