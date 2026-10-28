#!/usr/bin/env python3
"""Standalone offline Merkle verifier for PAMM settlement proofs."""
import argparse, json, hashlib, sys
DOMAIN = b"PAMM-SETTLEMENT-V1:"

def h(data: bytes) -> str:
    return hashlib.sha256(DOMAIN + data).hexdigest()

def verify(leaf_hash_hex, path, expected_root) -> bool:
    cur = leaf_hash_hex
    for step in path:
        sib = step["sibling"]
        if step["position"] == "right":
            cur = h(bytes.fromhex(cur) + bytes.fromhex(sib))
        elif step["position"] == "left":
            cur = h(bytes.fromhex(sib) + bytes.fromhex(cur))
        else:
            raise ValueError(f"invalid position: {step['position']}")
    return cur == expected_root

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--leaf-hash", required=True)
    v.add_argument("--root", required=True)
    v.add_argument("--path", required=True)
    f = sub.add_parser("verify-file")
    f.add_argument("file")
    args = ap.parse_args()
    if args.cmd == "verify":
        path = json.loads(args.path)
        ok = verify(args.leaf_hash, path, args.root)
    else:
        with open(args.file) as fh:
            data = json.load(fh)
        ok = verify(data["leaf_hash"], data["path"], data["root_hash"])
        if ok: print(f"ROOT: {data['root_hash']}")
    print("PROOF VERIFIED" if ok else "PROOF FAILED")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
