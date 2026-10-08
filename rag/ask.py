"""Answer a question using the closest chunks from pgvector and Llama on the lab GPU."""
import os
import sys

import psycopg
import requests

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
DSN = os.environ.get("PG_DSN", "host=127.0.0.1 port=15432 dbname=rag user=rag")  # password comes from PGPASSWORD
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "llama3.2:3b"
TOP_K = 4


def embed(text):
    r = requests.post(f"{OLLAMA}/api/embed",
                      json={"model": EMBED_MODEL, "input": [text]}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def to_vector(values):
    return "[" + ",".join(str(x) for x in values) + "]"


def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python ask.py "your question"')
    question = " ".join(sys.argv[1:])
    qvec = to_vector(embed("search_query: " + question))

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT source, chunk, embedding <=> %s::vector AS distance "
            "FROM chunks ORDER BY distance LIMIT %s",
            (qvec, TOP_K),
        )
        rows = cur.fetchall()
    if not rows:
        sys.exit("No chunks in the database yet. Run ingest.py first.")

    context = "\n\n---\n\n".join(f"[{source}]\n{chunk}" for source, chunk, _ in rows)
    prompt = (
        "You answer questions about a home AI lab using only the notes below. "
        "If the notes don't contain the answer, say you don't know.\n\n"
        f"NOTES:\n{context}\n\nQUESTION: {question}\nANSWER:"
    )
    r = requests.post(f"{OLLAMA}/api/generate",
                      json={"model": CHAT_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.2}},
                      timeout=300)
    r.raise_for_status()

    print(r.json()["response"].strip())
    print("\nSources:")
    for source, chunk, distance in rows:
        preview = " ".join(chunk.split())[:70]
        print(f"  {distance:.3f}  {source}  {preview}...")


if __name__ == "__main__":
    main()
