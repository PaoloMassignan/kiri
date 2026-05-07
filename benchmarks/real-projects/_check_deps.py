import chromadb, sys

# EphemeralClient
c = chromadb.EphemeralClient()
col = c.get_or_create_collection("test", metadata={"hnsw:space": "cosine"})
col.upsert(ids=["a"], embeddings=[[0.1]*384], metadatas=[{"source_file": "x", "chunk_index": "0"}])
r = col.query(query_embeddings=[[0.1]*384], n_results=1, include=["distances", "metadatas"])
sim = round(1.0 - r["distances"][0][0] / 2.0, 4)
print(f"EphemeralClient ok, similarity={sim}")

# Ollama L3
import httpx
try:
    resp = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": "qwen2.5:3b", "prompt": "Reply with just the word: yes", "stream": False},
        timeout=15,
    )
    print(f"Ollama ok, status={resp.status_code}, response={resp.json().get('response','')[:40]!r}")
except Exception as e:
    print(f"Ollama unavailable: {e}")
