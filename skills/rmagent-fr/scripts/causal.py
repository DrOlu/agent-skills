#!/usr/bin/env python3
"""Causal graph builder — hops are a list; attacks are a graph.

Builds the graph at case-close time from path.json + the hop index:

  node: (host, principal, logonid)
  edge: 4648 (became), 4624 (logged on), netedges (connected to), share access

Answers the question that matters: "everything reachable from the initial
compromise within N hops." That's blast radius, computed from kilobytes.

Renders as ASCII (the trajectory already produces trees) or emits DOT for a
real diagram in the case file.
"""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class Node:
    host: str
    principal: str
    logonid: str | None = None
    label: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}/{self.principal}" + (f"/{self.logonid}" if self.logonid else "")


@dataclass
class Edge:
    src: str            # node key
    dst: str            # node key
    kind: str           # 4624 | 4648 | conn | task | service | wmi | share
    t: str = ""
    detail: str = ""


@dataclass
class CausalGraph:
    nodes: dict = field(default_factory=dict)   # key -> Node
    edges: list = field(default_factory=list)   # [Edge]
    _adj: dict = field(default_factory=lambda: defaultdict(list))

    def add_node(self, host: str, principal: str, logonid: str | None = None) -> Node:
        n = Node(host=host, principal=principal, logonid=logonid)
        if n.key not in self.nodes:
            self.nodes[n.key] = n
        return self.nodes[n.key]

    def add_edge(self, src_host: str, src_principal: str, dst_host: str, dst_principal: str,
                 kind: str, t: str = "", detail: str = "",
                 src_logonid: str | None = None, dst_logonid: str | None = None) -> Edge:
        s = self.add_node(src_host, src_principal, src_logonid)
        d = self.add_node(dst_host, dst_principal, dst_logonid)
        e = Edge(src=s.key, dst=d.key, kind=kind, t=t, detail=detail)
        self.edges.append(e)
        self._adj[s.key].append((d.key, e))
        return e

    # ---------------------------------------------------------------- queries
    def blast_radius(self, origin_key: str, max_hops: int = 4) -> set[str]:
        """Everything reachable from origin within max_hops. THE blast-radius question."""
        if origin_key not in self.nodes:
            return set()
        seen = {origin_key}
        frontier = deque([(origin_key, 0)])
        while frontier:
            cur, depth = frontier.popleft()
            if depth >= max_hops:
                continue
            for nxt, _e in self._adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append((nxt, depth + 1))
        return seen

    def path_between(self, src_key: str, dst_key: str) -> list[str] | None:
        """Shortest causal path between two nodes (BFS)."""
        if src_key not in self.nodes or dst_key not in self.nodes:
            return None
        prev = {src_key: None}
        q = deque([src_key])
        while q:
            cur = q.popleft()
            if cur == dst_key:
                path = []
                while cur is not None:
                    path.append(cur)
                    cur = prev[cur]
                return list(reversed(path))
            for nxt, _e in self._adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        return None

    def in_edges(self, node_key: str) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_key]

    def out_edges(self, node_key: str) -> list[Edge]:
        return [e for e in self.edges if e.src == node_key]

    def degree(self) -> dict:
        """Node degree — the hubs of the attack."""
        d = defaultdict(int)
        for e in self.edges:
            d[e.src] += 1
            d[e.dst] += 1
        return dict(d)

    # ---------------------------------------------------------------- render
    def render_ascii(self, origin_key: str | None = None, max_hops: int = 4) -> str:
        """ASCII tree from an origin (or the whole graph if no origin)."""
        if not self.nodes:
            return "(causal graph is empty)"
        if origin_key:
            reach = self.blast_radius(origin_key, max_hops)
            lines = [f"blast radius from {origin_key} (≤{max_hops} hops): {len(reach)} nodes", ""]
            visited = set()
            def walk(key: str, prefix: str, depth: int):
                if key in visited or depth > max_hops:
                    return
                visited.add(key)
                n = self.nodes[key]
                lines.append(f"{prefix}{n.host}/{n.principal}"
                             + (f" [{n.logonid}]" if n.logonid else ""))
                children = self._adj.get(key, [])
                for i, (ck, e) in enumerate(children):
                    last = (i == len(children) - 1)
                    mark = "└─ " if last else "├─ "
                    lines.append(f"{prefix}  {mark}({e.kind}) {e.detail[:40]}")
                    walk(ck, prefix + ("   " if last else "│  "), depth + 1)
            walk(origin_key, "", 0)
            return "\n".join(lines)
        # whole graph
        lines = [f"causal graph: {len(self.nodes)} nodes, {len(self.edges)} edges", ""]
        for e in self.edges:
            lines.append(f"  {e.src}  --{e.kind}-->  {e.dst}   {e.detail[:40]}")
        return "\n".join(lines)

    def render_dot(self) -> str:
        """DOT for Graphviz rendering in the case file."""
        lines = ["digraph causal {"]
        for k, n in self.nodes.items():
            lbl = f"{n.host}/{n.principal}" + (f"\\n{n.logonid}" if n.logonid else "")
            lines.append(f'  "{k}" [label="{lbl}"];')
        for e in self.edges:
            lines.append(f'  "{e.src}" -> "{e.dst}" [label="{e.kind}"];')
        lines.append("}")
        return "\n".join(lines)


# ---------------------------------------------------------------- build from case
def build_from_case(case_dir: Path) -> CausalGraph:
    """Build the causal graph from a case's path.json + hop index entries."""
    g = CausalGraph()
    pj = Path(case_dir) / "path.json"
    if pj.exists():
        try:
            hops = json.loads(pj.read_text())
        except (json.JSONDecodeError, OSError):
            hops = []
        for h in hops:
            wid = h.get("witness", "?")
            if h.get("skill") == "edges":
                g.add_node(wid, "Administrator")
                g.add_node(wid, "SYSTEM")
            elif h.get("skill") == "explain":
                for _ in range(h.get("identity_changes", 0)):
                    g.add_edge(wid, "Administrator", wid, "unknown", "identity")
    return g


def build_from_hop_index(case: str, index_entries: list[dict]) -> CausalGraph:
    """Build the causal graph from hop-index entries for one case."""
    g = CausalGraph()
    for e in index_entries:
        if e.get("case") != case:
            continue
        host = e.get("host", "?")
        principal = e.get("principal", "?")
        kind = e.get("kind", "?")
        detail = e.get("detail", "")
        logonid = e.get("logonid")
        if kind == "4648":
            # explicit cred: who became whom, possibly on another host
            g.add_edge(host, principal, host, detail or "target", "4648", e.get("t", ""), detail)
        else:
            g.add_node(host, principal, logonid)
            if kind == "conn" and detail:
                g.add_edge(host, principal, detail, principal, "conn", e.get("t", ""), detail)
    return g


def render_png(dot: str, out_path) -> bool:
    """Render DOT to PNG via graphviz if available. Best-effort; returns success."""
    import subprocess, shutil, tempfile
    if not shutil.which("dot"):
        return False
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
            f.write(dot)
            dotfile = f.name
        r = subprocess.run(["dot", "-Tpng", dotfile, "-o", str(out_path)],
                           capture_output=True, timeout=15)
        import os
        os.unlink(dotfile)
        return r.returncode == 0
    except Exception:
        return False
