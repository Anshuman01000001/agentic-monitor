import os
import json
import logging
from typing import List

logger = logging.getLogger(__name__)

# Globals kept in module for reuse
_client = None
_collection = None
_embedder = None
_index_file = ".runbook_index.json"


def _load_index(chroma_dir: str) -> dict:
    path = os.path.join(chroma_dir, _index_file)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to read runbook index")
    return {}


def _save_index(chroma_dir: str, idx: dict):
    path = os.path.join(chroma_dir, _index_file)
    try:
        with open(path, "w") as f:
            json.dump(idx, f)
    except Exception:
        logger.exception("Failed to write runbook index")


def init_rag_store(chroma_dir: str):
    """Initialize or update the persistent ChromaDB store with runbook chunks.

    Splits markdown files on '##' headers and embeds using sentence-transformers.
    Only re-embeds files that have changed since last run.
    """
    global _client, _collection, _embedder

    os.makedirs(chroma_dir, exist_ok=True)
    logger.info("Initializing RAG store at %s", chroma_dir)

    # Only attempt to load heavy ML libraries if runbooks exist

    # Load previous index of mtimes
    index = _load_index(chroma_dir)

    runbooks_dir = os.path.join(os.getcwd(), "runbooks")
    if not os.path.isdir(runbooks_dir):
        logger.warning("No runbooks directory found at %s", runbooks_dir)
        return

    # Lazy import heavy dependencies now that we know runbooks exist
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        logger.exception("Failed to import sentence-transformers; embeddings will be disabled")
        SentenceTransformer = None

    try:
        import chromadb
    except Exception:
        logger.exception("Failed to import chromadb; retrieval will be disabled")
        chromadb = None

    try:
        if SentenceTransformer:
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        else:
            _embedder = None
    except Exception:
        logger.exception("Failed to load sentence-transformers model")
        _embedder = None

    try:
        if chromadb:
            _client = chromadb.PersistentClient(path=chroma_dir)
            _collection = _client.get_or_create_collection(name="runbooks")
        else:
            _client = None
            _collection = None
    except Exception:
        logger.exception("Failed to initialize chromadb client/collection")
        _client = None
        _collection = None

    for fname in os.listdir(runbooks_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(runbooks_dir, fname)
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            continue
        prev = index.get(fname)
        if prev and prev.get("mtime") == mtime:
            logger.debug("Runbook unchanged: %s", fname)
            continue

        # (Re-)embed this file
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            logger.exception("Failed to read runbook %s", path)
            continue

        # Split on '##' headers for chunks
        parts = [p.strip() for p in content.split("##") if p.strip()]
        if not parts:
            continue

        # Prepare embeddings
        if not _embedder or not _collection:
            logger.warning("Embedder or collection not available; skipping embedding for %s", fname)
            continue

        try:
            embeddings = _embedder.encode(parts, convert_to_numpy=True)
            ids = [f"{fname}__{i}" for i in range(len(parts))]
            metadatas = [{"file": fname, "chunk_index": i} for i in range(len(parts))]
            # Remove previous chunks for this file if any
            try:
                _collection.delete(where={"file": [fname]})
            except Exception:
                # delete may not be supported; ignore
                pass
            _collection.add(ids=ids, documents=parts, embeddings=embeddings.tolist(), metadatas=metadatas)
            index[fname] = {"mtime": mtime, "chunks": len(parts)}
            logger.info("Indexed runbook %s with %d chunks", fname, len(parts))
        except Exception:
            logger.exception("Failed to embed runbook %s", fname)

    _save_index(chroma_dir, index)


def get_runbook_context(event_description: str) -> str:
    """Embed `event_description` and retrieve top 2 most similar runbook chunks.

    Returns concatenated string (possibly empty).
    """
    global _client, _collection, _embedder
    if not _collection or not _embedder:
        logger.debug("RAG components not initialized")
        return ""

    try:
        q_emb = _embedder.encode([event_description], convert_to_numpy=True)
        res = _collection.query(query_embeddings=q_emb.tolist(), n_results=2)
        # results structure: dict with 'documents' key
        docs = []
        for row in res.get("documents", []):
            if isinstance(row, list):
                docs.extend(row)
        # Fallback older API style
        if not docs and isinstance(res.get("ids"), list):
            docs = res.get("documents", [])

        return "\n\n".join(docs) if docs else ""
    except Exception:
        logger.exception("Failed to retrieve runbook context")
        return ""


def retrieve_runbook_context(query: str, top_k: int = 2) -> List[str]:
    ctx = get_runbook_context(query)
    if not ctx:
        return []
    return [ctx]
