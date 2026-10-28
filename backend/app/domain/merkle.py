"""P-4: Confidential Merkle verification — domain-separated SHA-256."""
import hashlib

DOMAIN = b"PAMM-SETTLEMENT-V1:"

def h(data: bytes) -> str:
    return hashlib.sha256(DOMAIN + data).hexdigest()

def canonicalize(pairs: dict) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))

def leaf_hash(pairs: dict):
    blob = canonicalize(pairs)
    return blob, h(blob.encode("utf-8"))

def build_tree(leaf_hashes):
    if not leaf_hashes:
        raise ValueError("Cannot build tree from empty leaves")
    levels = [list(leaf_hashes)]
    current = list(leaf_hashes)
    while len(current) > 1:
        if len(current) % 2 == 1:
            current.append(current[-1])
        nxt = []
        for i in range(0, len(current), 2):
            nxt.append(h(bytes.fromhex(current[i]) + bytes.fromhex(current[i + 1])))
        levels.append(nxt)
        current = nxt
    return current[0], levels

def inclusion_proof(leaf_index, levels):
    proof = []
    idx = leaf_index
    for level in levels[:-1]:
        if idx % 2 == 0:
            sib_idx = idx + 1 if idx + 1 < len(level) else idx
            proof.append({"sibling": level[sib_idx], "position": "right"})
        else:
            proof.append({"sibling": level[idx - 1], "position": "left"})
        idx //= 2
    return proof

def verify_proof(leaf_hash_hex, proof, expected_root) -> bool:
    cur = leaf_hash_hex
    for step in proof:
        sib = step["sibling"]
        if step["position"] == "right":
            cur = h(bytes.fromhex(cur) + bytes.fromhex(sib))
        else:
            cur = h(bytes.fromhex(sib) + bytes.fromhex(cur))
    return cur == expected_root
