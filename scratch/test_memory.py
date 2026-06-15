import sys
import os
import re
import numpy as np

def test_fallback(text_clean, dim=1024):
    vector = [0.0] * dim
    
    def _det_hash(s: str) -> int:
        h = 0
        for char in s:
            h = (31 * h + ord(char)) & 0xFFFFFFFF
        return h

    words = re.findall(r"\w+", text_clean.lower())
    for w in words:
        idx = _det_hash(w) % dim
        vector[idx] += 1.0

    for i in range(len(text_clean) - 1):
        bigram = text_clean[i:i+2].lower()
        idx = _det_hash(bigram) % dim
        vector[idx] += 0.2

    arr = np.array(vector)
    norm = np.linalg.norm(arr)
    if norm > 0.0:
        return list(arr / norm)
    return [0.0] * dim

def cosine_similarity(v1, v2):
    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

ep1 = "My name is John and I live in Alabama."
ep2 = "I have two dogs named Max and Charlie."
query = "Do I have pets?"

for d in [128, 256, 512, 1024]:
    qv = test_fallback(query, d)
    v1 = test_fallback(ep1, d)
    v2 = test_fallback(ep2, d)
    print(f"Dimension {d}:")
    print(f"  Similarity Ep 1: {cosine_similarity(qv, v1):.4f}")
    print(f"  Similarity Ep 2: {cosine_similarity(qv, v2):.4f}")
