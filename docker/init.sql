-- Initialise the pgvector extension so embeddings and LangGraph
-- checkpoints (which use vector columns) work out of the box.
CREATE EXTENSION IF NOT EXISTS vector;