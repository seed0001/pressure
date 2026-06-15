import json
import os
import pathlib
import time
import urllib.request
import numpy as np
import re

# Data directory
_DATA_DIR = pathlib.Path(os.path.dirname(os.path.abspath(__file__))) / "data"
_DATA_DIR.mkdir(exist_ok=True)

# Cache of embeddings to save API calls
_EMBEDDINGS_CACHE_FILE = _DATA_DIR / "embeddings_cache.json"
_EPISODIC_MEMORY_FILE = _DATA_DIR / "episodic_memory.json"

_FALLBACK_DIM = 512

_embeddings_cache = {}
if _EMBEDDINGS_CACHE_FILE.exists():
    try:
        with open(_EMBEDDINGS_CACHE_FILE, "r", encoding="utf-8") as f:
            _embeddings_cache = json.load(f)
    except Exception as e:
        print(f"[Memory] Warning: Could not load embeddings cache: {e}")

_episodes = []
if _EPISODIC_MEMORY_FILE.exists():
    try:
        with open(_EPISODIC_MEMORY_FILE, "r", encoding="utf-8") as f:
            _episodes = json.load(f)
    except Exception as e:
        print(f"[Memory] Warning: Could not load episodic memory: {e}")

def save_caches():
    try:
        with open(_EMBEDDINGS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_embeddings_cache, f, indent=1)
        with open(_EPISODIC_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(_episodes, f, indent=1)
    except Exception as e:
        print(f"[Memory] Error saving caches: {e}")

def get_embedding(text: str, model: str = "llama3.2") -> list[float]:
    """Get vector embedding, utilizing cache or Ollama API with character-distribution fallback."""
    text_clean = text.strip()
    if not text_clean:
        return [0.0] * _FALLBACK_DIM
        
    if text_clean in _embeddings_cache:
        return _embeddings_cache[text_clean]
        
    # Try Ollama /api/embed (modern)
    try:
        url = "http://localhost:11434/api/embed"
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": model, "input": text_clean}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if "embeddings" in res and res["embeddings"]:
                vector = res["embeddings"][0]
                _embeddings_cache[text_clean] = vector
                return vector
    except Exception:
        pass

    # Try Ollama /api/embeddings (legacy)
    try:
        url = "http://localhost:11434/api/embeddings"
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": model, "prompt": text_clean}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if "embedding" in res:
                vector = res["embedding"]
                _embeddings_cache[text_clean] = vector
                return vector
    except Exception:
        pass

    # Fallback: deterministic character-distribution and word-hash vector (_FALLBACK_DIM dimensions)
    # This provides a deterministic vector space fallback in offline/unsupported states
    # where similar text distributions yield high cosine similarity.
    vector = [0.0] * _FALLBACK_DIM
    
    def _det_hash(s: str) -> int:
        h = 0
        for char in s:
            h = (31 * h + ord(char)) & 0xFFFFFFFF
        return h

    # Tokenize words
    words = re.findall(r"\w+", text_clean.lower())
    for w in words:
        idx = _det_hash(w) % _FALLBACK_DIM
        vector[idx] += 1.0

    # Tokenize character bigrams
    for i in range(len(text_clean) - 1):
        bigram = text_clean[i:i+2].lower()
        idx = _det_hash(bigram) % _FALLBACK_DIM
        vector[idx] += 0.2

    # Normalize
    arr = np.array(vector)
    norm = np.linalg.norm(arr)
    if norm > 0.0:
        vector = list(arr / norm)
    else:
        vector = [0.0] * _FALLBACK_DIM

    _embeddings_cache[text_clean] = vector
    return vector


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def add_episode(tick: int, user_text: str, assistant_reply: str):
    """Save an episode (conversation exchange) into episodic memory."""
    user_clean = (user_text or "").strip()
    assistant_clean = (assistant_reply or "").strip()
    if not user_clean and not assistant_clean:
        return
        
    episode_text = f"User: {user_clean}\nAgent: {assistant_clean}"
    # Compute embedding
    vector = get_embedding(episode_text)
    user_vector = get_embedding(user_clean) if user_clean else None
    
    _episodes.append({
        "tick": tick,
        "timestamp": time.time(),
        "text": episode_text,
        "embedding": vector,
        "user_embedding": user_vector
    })
    
    # Keep last 100 episodes
    if len(_episodes) > 100:
        _episodes.pop(0)
        
    save_caches()

def semantic_search_episodes(query_text: str, k: int = 3) -> str:
    """Retrieve semantically relevant conversation episodes from memory."""
    if not _episodes:
        return ""
        
    query_vector = get_embedding(query_text)
    matches = []
    for ep in _episodes:
        sim = cosine_similarity(query_vector, ep["embedding"])
        if ep.get("user_embedding"):
            user_sim = cosine_similarity(query_vector, ep["user_embedding"])
            if user_sim > sim:
                sim = user_sim
        matches.append((sim, ep))
        
    # Sort by similarity descending
    matches.sort(key=lambda x: -x[0])
    
    top_matches = [m for m in matches if m[0] > 0.3][:k]
    if not top_matches:
        return ""
        
    lines = []
    for sim, ep in reversed(top_matches): # Older/relevant first
        lines.append(f"  [Similarity {sim:.2f} | Tick {ep['tick']}]:\n{ep['text']}")
        
    return "Relevant past dialogue episodes:\n" + "\n---\n".join(lines)


def semantic_search_graph(graph, query_text: str, max_nodes: int = 6) -> str:
    """Perform semantic vector-similarity search over knowledge graph nodes and facts."""
    if not graph.nodes:
        return ""
        
    query_vector = get_embedding(query_text)
    
    # Calculate similarity with each node
    node_similarities = []
    for nid, node in graph.nodes.items():
        # Node similarity is the max similarity of either the node label or any of its facts
        best_sim = cosine_similarity(query_vector, get_embedding(node.label))
        
        # Check facts
        for fact in node.facts:
            sim = cosine_similarity(query_vector, get_embedding(fact))
            if sim > best_sim:
                best_sim = sim
                
        node_similarities.append((best_sim, node))
        
    # Sort by similarity descending
    node_similarities.sort(key=lambda x: -x[0])
    
    seen_ids = set()
    lines = []
    
    for sim, node in node_similarities:
        if sim < 0.35: # Similarity threshold
            break
        if node.id in seen_ids:
            continue
            
        seen_ids.add(node.id)
        fact_str = "; ".join(node.facts) if node.facts else "no facts yet"
        lines.append(f"  [{node.type}] {node.label} (relevance={sim:.2f}): {fact_str}")
        
        # Include neighbors
        for neighbor_label, relation, direction in graph.neighbors(node.label)[:3]:
            n2 = graph.nodes.get(_normalize(neighbor_label))
            n2_facts = ("; ".join(n2.facts[:2])) if n2 and n2.facts else ""
            arrow = "->" if direction == "out" else "<-"
            lines.append(
                f"    {arrow} {relation} {arrow} {neighbor_label}"
                + (f": {n2_facts}" if n2_facts else "")
            )
            
        if len(seen_ids) >= max_nodes:
            break
            
    if not lines:
        return ""
        
    save_caches() # Save any newly computed embeddings
    return "What the agent already knows (semantically retrieved):\n" + "\n".join(lines)

def _normalize(text: str) -> str:
    """Normalize labels to standard IDs."""
    return re.sub(r"\s+", "_", text.strip().lower())

def clear_memory():
    """Wipe all episodic memory and embeddings cache from memory and disk."""
    global _episodes, _embeddings_cache
    _episodes = []
    _embeddings_cache = {}
    
    # Delete files
    for f in [_EPISODIC_MEMORY_FILE, _EMBEDDINGS_CACHE_FILE]:
        try:
            if f.exists():
                f.unlink()
        except Exception as e:
            print(f"[Memory] Error deleting {f}: {e}")

