"""Cycle-aware layout: a large embedded cycle is collapsed to a compact band; a small one is
left to the engine's loop-curl."""
from tools.procesio.layout import cycles, engine


def _maxedge(P, edges):
    return max((abs(P[e["source"]]["x"] - P[e["dest"]]["x"])
                + abs(P[e["source"]]["y"] - P[e["dest"]]["y"])) for e in edges)


def _chain_with_cycle(n):
    """a -> b -> c -> [k0..k{n-1} cycle] -> out."""
    nodes = [{"id": x} for x in ("a", "b", "c", "out")] + [{"id": f"k{i}"} for i in range(n)]
    edges = [{"source": "a", "dest": "b"}, {"source": "b", "dest": "c"},
             {"source": "c", "dest": "k0"}, {"source": "k2", "dest": "out"}]
    for i in range(n):
        edges.append({"source": f"k{i}", "dest": f"k{(i + 1) % n}"})   # k(n-1) -> k0 closes it
    return nodes, edges


def test_sccs_finds_the_cycle():
    nodes, edges = _chain_with_cycle(8)
    comps = cycles._sccs([n["id"] for n in nodes],
                         [(e["source"], e["dest"]) for e in edges])
    big = [c for c in comps if len(c) > 1]
    assert len(big) == 1 and set(big[0]) == {f"k{i}" for i in range(8)}


def test_large_cycle_collapsed_and_expanded():
    """An 8-node cycle (>= MIN_CYCLE) is collapsed to a meta-node and expanded back: every real
    node is placed, the meta-node never leaks into the output, and it's deterministic. (The
    canvas-spanning-edge win is topology-dependent — proven live on Get-info-SalesOMMO where the
    main flow interleaves the cycle: max edge 2538 -> 1280px — not on a standalone ring.)"""
    nodes, edges = _chain_with_cycle(8)
    a1 = cycles.layout(nodes, edges, opts=None, subset=None, dispatch_layout=engine.layout)
    a2 = cycles.layout(nodes, edges, opts=None, subset=None, dispatch_layout=engine.layout)
    assert set(a1["positions"]) == {n["id"] for n in nodes}   # all real nodes placed
    assert cycles._META not in a1["positions"]                # meta-node removed on expand
    assert a1["positions"] == a2["positions"]                 # deterministic


def test_small_cycle_left_untouched():
    """A 4-node cycle is below MIN_CYCLE (8) — cycle-aware must be a pure pass-through so the
    engine's loop-curl still owns it."""
    nodes, edges = _chain_with_cycle(4)
    plain = engine.layout(nodes, edges)
    aware = cycles.layout(nodes, edges, opts=None, subset=None, dispatch_layout=engine.layout)
    assert aware["positions"] == plain["positions"]


def test_subset_mode_passes_through():
    nodes, edges = _chain_with_cycle(8)
    aware = cycles.layout(nodes, edges, opts=None, subset=["b"], dispatch_layout=engine.layout)
    plain = engine.layout(nodes, edges, subset=["b"])
    assert aware["positions"] == plain["positions"]


def test_large_cycle_prefers_ring_two_rows():
    """The reference ring pattern: a large collapsible cycle expands as a compact TWO-ROW ring
    (forward row + return row), not a wide one-row band, when that costs no crossings.
    (A mid-ring exit can make the band win -- that is the score guard's call.)"""
    nodes = [{"id": x} for x in ("a", "b")] + [{"id": f"k{i}"} for i in range(8)]
    edges = ([{"source": "a", "dest": "b"}, {"source": "b", "dest": "k0"}]
             + [{"source": f"k{i}", "dest": f"k{(i + 1) % 8}"} for i in range(8)])
    res = cycles.layout(nodes, edges, opts=None, subset=None, dispatch_layout=engine.layout)
    ys = sorted({round(res["positions"][f"k{i}"]["y"]) for i in range(8)})
    assert len(ys) == 2                                   # two rows...
    xs = {round(res["positions"][f"k{i}"]["x"]) for i in range(8)}
    assert len(xs) <= 4                                   # ...folded to half the width
