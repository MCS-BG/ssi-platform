"""Answer a question using the closest chunks from pgvector and Llama on the lab GPU.

Day 8b: one question is one trace. Run it through opentelemetry-instrument and the whole
question shows up in Langfuse as a "rag-ask" trace: the embedding call, the pgvector
retrieval and the Llama generation (with model, prompt, answer and token counts).
"""
import os
import sys

import psycopg
import requests

from llmtrace import observation, set_ollama_response, set_output

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
DSN = os.environ.get("PG_DSN", "host=127.0.0.1 port=15432 dbname=rag user=rag")  # password comes from PGPASSWORD
EMBED_MODEL = "nomic-embed-text"
# Keep the small embedding model loaded in Ollama ("-1m" = until Ollama restarts or needs the VRAM).
# Only embedding calls send this; chat models keep the server default (OLLAMA_KEEP_ALIVE=10m).
EMBED_KEEP_ALIVE = os.environ.get("EMBED_KEEP_ALIVE", "-1m")
CHAT_MODEL = "llama3.2:3b"
TEMPERATURE = 0.2
TOP_K = 4


def embed(text):
    with observation("ollama embed", "embedding", input=text, model=EMBED_MODEL,
                     operation="embeddings") as span:
        r = requests.post(f"{OLLAMA}/api/embed",
                          json={"model": EMBED_MODEL, "input": [text], "keep_alive": EMBED_KEEP_ALIVE},
                          timeout=300)
        r.raise_for_status()
        body = r.json()
        set_ollama_response(span, body)
        vector = body["embeddings"][0]
        set_output(span, {"dimensions": len(vector)})
        return vector


def to_vector(values):
    return "[" + ",".join(str(x) for x in values) + "]"


def retrieve(question, qvec):
    with observation("pgvector search", "retriever", input={"query": question, "top_k": TOP_K}) as span:
        with psycopg.connect(DSN) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT source, chunk, embedding <=> %s::vector AS distance "
                "FROM chunks ORDER BY distance LIMIT %s",
                (qvec, TOP_K),
            )
            rows = cur.fetchall()
        set_output(span, [{"source": s, "distance": round(float(d), 4)} for s, _, d in rows])
        return rows


def generate(prompt):
    with observation("ollama generate", "generation", input=prompt, model=CHAT_MODEL,
                     operation="text_completion", **{"gen_ai.request.temperature": TEMPERATURE}) as span:
        r = requests.post(f"{OLLAMA}/api/generate",
                          json={"model": CHAT_MODEL, "prompt": prompt, "stream": False,
                                "options": {"temperature": TEMPERATURE}},
                          timeout=300)
        r.raise_for_status()
        body = r.json()
        set_ollama_response(span, body)
        answer = body["response"].strip()
        set_output(span, answer)
        return answer


def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python ask.py "your question"')
    question = " ".join(sys.argv[1:])

    with observation("rag-ask", "chain", input=question, trace_name="rag-ask") as root:
        qvec = to_vector(embed("search_query: " + question))
        rows = retrieve(question, qvec)
        if not rows:
            sys.exit("No chunks in the database yet. Run ingest.py first.")

        context = "\n\n---\n\n".join(f"[{source}]\n{chunk}" for source, chunk, _ in rows)
        prompt = (
            "You answer questions about a home AI lab using only the notes below. "
            "If the notes don't contain the answer, say you don't know.\n\n"
            f"NOTES:\n{context}\n\nQUESTION: {question}\nANSWER:"
        )
        answer = generate(prompt)
        set_output(root, answer)

    print(answer)
    print("\nSources:")
    for source, chunk, distance in rows:
        preview = " ".join(chunk.split())[:70]
        print(f"  {distance:.3f}  {source}  {preview}...")


if __name__ == "__main__":
    main()
