"""One-shot ingest runner for legal docs → Chroma."""

from app.services.rag.ingest import ingest_directory

if __name__ == "__main__":
    n = ingest_directory()
    print(f"CHUNKS={n}", flush=True)
