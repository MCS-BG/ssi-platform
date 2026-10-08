"""Chunk Markdown files, embed them with Ollama, and store them in pgvector.

Day 8b: run through opentelemetry-instrument, one ingest run is one "rag-ingest" trace in
Langfuse, with one embedding observation per file.
"""
import glob
import os
import sys

import psycopg
import requests

from llmtrace import observation, set_ollama_response, set_output

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
DSN = os.environ.get("PG_DSN", "host=127.0.0.1 port=15432 dbname=rag user=rag")  # password comes from PGPASSWORD
EMBED_MODEL = "nomic-embed-text"
# Keep the embedding model loaded (see ask.py). Chat models are not affected.
EMBED_KEEP_ALIVE = os.environ.get("EMBED_KEEP_ALIVE", "-1m")
MAX_CHARS = 1200


def chunk_markdown(text):
    """Group paragraphs into chunks of up to MAX_CHARS characters."""
    chunks, current = [], ""
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            chunks.append(current)
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current)
    return chunks


def embed(texts, source=None):
    with observation("ollama embed", "embedding", input={"source": source, "chunks": len(texts)},
                     model=EMBED_MODEL, operation="embeddings") as span:
        r = requests.post(f"{OLLAMA}/api/embed",
                          json={"model": EMBED_MODEL, "input": texts, "keep_alive": EMBED_KEEP_ALIVE},
                          timeout=300)
        r.raise_for_status()
        body = r.json()
        set_ollama_response(span, body)
        set_output(span, {"vectors": len(body["embeddings"])})
        return body["embeddings"]


def to_vector(values):
    return "[" + ",".join(str(x) for x in values) + "]"


def main():
    folder = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DOCS_DIR", "/docs"))
    files = sorted(glob.glob(os.path.join(folder, "*.md")))
    if not files:
        sys.exit(f"No .md files found in {folder}")

    with observation("rag-ingest", "chain", input={"folder": folder, "files": len(files)},
                     trace_name="rag-ingest") as root, psycopg.connect(DSN) as conn:
        total = 0
        for path in files:
            source = os.path.basename(path)
            with open(path, encoding="utf-8") as f:
                chunks = chunk_markdown(f.read())
            vectors = embed(["search_document: " + c for c in chunks], source=source)
            with conn.cursor() as cur:
                # Re-running replaces a file's chunks instead of duplicating them.
                cur.execute("DELETE FROM chunks WHERE source = %s", (source,))
                cur.executemany(
                    "INSERT INTO chunks (source, chunk, embedding) VALUES (%s, %s, %s::vector)",
                    [(source, c, to_vector(v)) for c, v in zip(chunks, vectors)],
                )
            conn.commit()
            total += len(chunks)
            print(f"{source}: {len(chunks)} chunks stored")
        set_output(root, {"files": len(files), "chunks": total})

if __name__ == "__main__":
    main()
