from app.domain import merkle

def test_canonicalization_sorted():
    assert merkle.canonicalize({"b": "2", "a": "1"}) == merkle.canonicalize({"a": "1", "b": "2"}) == "a=1\nb=2"

def test_domain_separation():
    import hashlib
    assert merkle.h(b"a=1") != hashlib.sha256(b"a=1").hexdigest()

def test_root_single_leaf():
    blob, lh = merkle.leaf_hash({"a": "1"})
    root, levels = merkle.build_tree([lh])
    assert root == lh and len(levels) == 1

def test_root_two_leaves():
    _, l1 = merkle.leaf_hash({"a": "1"})
    _, l2 = merkle.leaf_hash({"a": "2"})
    expected = merkle.h(bytes.fromhex(l1) + bytes.fromhex(l2))
    root, levels = merkle.build_tree([l1, l2])
    assert root == expected

def test_inclusion_proof_verifies():
    leaves = [merkle.leaf_hash({"i": str(i)})[1] for i in range(5)]
    root, levels = merkle.build_tree(leaves)
    proof = merkle.inclusion_proof(2, levels)
    assert merkle.verify_proof(leaves[2], proof, root)

def test_inclusion_proof_tampered_fails():
    leaves = [merkle.leaf_hash({"i": str(i)})[1] for i in range(5)]
    root, levels = merkle.build_tree(leaves)
    proof = merkle.inclusion_proof(2, levels)
    assert not merkle.verify_proof(leaves[1], proof, root)

def test_odd_leaf_count_duplicated():
    leaves = [merkle.leaf_hash({"i": str(i)})[1] for i in range(3)]
    root, levels = merkle.build_tree(leaves)
    assert len(levels[0]) == 3 and len(levels[1]) == 2
    for i in range(3):
        assert merkle.verify_proof(leaves[i], merkle.inclusion_proof(i, levels), root)
