import copy
from pathlib import Path
from typing import Optional
import tempfile
import subprocess

from mathlibtools.file_status import FileStatus

import networkx as nx # type: ignore

class ImportGraph(nx.DiGraph):
    def __init__(self, base_path: Optional[Path] = None) -> None:
        """A Lean project import graph."""
        super().__init__(self)
        self.base_path = base_path or Path('.')

    def to_dot(self, path: Optional[Path] = None) -> None:
        """Writes itself to a graphviz dot file."""
        path = path or self.base_path/'import_graph.dot'
        nx.drawing.nx_pydot.to_pydot(self).write_dot(str(path))

    def to_rawdot(self, path: Optional[Path] = None) -> None:
        """Writes itself to a raw dot file (without layout)."""
        path = path or self.base_path/'import_graph.rawdot'
        nx.drawing.nx_pydot.write_dot(self, str(path))

    def to_gexf(self, path: Optional[Path] = None) -> None:
        """Writes itself to a gexf dot file, suitable for Gephi."""
        path = path or self.base_path/'import_graph.gexf'
        modified = copy.deepcopy(self)
        for _, attrs in modified.nodes(data=True):
            status: Optional[FileStatus] = attrs.get("status")
            if status is None:
                attrs["status"] = ""
            else:
                attrs["status"] = status.to_gexf()
            if "fillcolor" in attrs and attrs["fillcolor"] is None:
                attrs.pop("fillcolor")
        nx.write_gexf(modified, str(path))

    def to_graphml(self, path: Optional[Path] = None) -> None:
        """Writes itself to a gexf dot file, suitable for yEd."""
        path = path or self.base_path/'import_graph.graphml'
        nx.write_graphml(self, str(path))

    def write(self, path: Path):
        if path.suffix == '.dot':
            self.to_dot(path)
        elif path.suffix == '.rawdot':
            self.to_rawdot(path)
        elif path.suffix == '.gexf':
            self.to_gexf(path)
        elif path.suffix == '.graphml':
            self.to_graphml(path)
        elif path.suffix in ['.pdf', '.svg', '.png']:
            dot_format = '-T' + path.suffix[1:]
            with tempfile.TemporaryDirectory() as tmpdirname:
                tmpf = Path(tmpdirname)/'tmp.dot'
                self.to_dot(tmpf)
                with path.open('w') as outf:
                    subprocess.run(['dot', dot_format, str(tmpf)],
                                   stdout=outf)
        else:
            raise ValueError('Unsupported graph output format. '
                             'Use .dot, .rawdot, .gexf, .graphml or a valid '
                             'graphviz output format (eg. .pdf).')

    def ancestors(self, node: str) -> 'ImportGraph':
        """Returns the subgraph leading to node."""
        H = self.subgraph(nx.ancestors(self, node).union([node]))
        H.base_path = self.base_path
        return H

    def descendants(self, node: str) -> 'ImportGraph':
        """Returns the subgraph descending from node."""
        H = self.subgraph(nx.descendants(self, node).union([node]))
        H.base_path = self.base_path
        return H

    def path(self, start: str, end: str) -> 'ImportGraph':
        """Returns the subgraph descending from the start node and used by the
        end node."""
        D = self.descendants(start)
        A = self.ancestors(end)
        H = self.subgraph(set(D.nodes).intersection(A.nodes))
        H.base_path = self.base_path
        return H

    def exclude_tactics(self) -> 'ImportGraph':
        """Removes all files in src/tactic/ and src/meta/ from the graph,
        except tactic.basic and tactic.core (but adds extra edges to reflect transitive dependencies)."""
        H = self
        to_delete = [n for n in H.nodes if
            n != 'tactic.basic' and n != 'tactic.core' and str.startswith(n, ('tactic.', 'meta.'))]
        for n in to_delete:
            parents = [k for (k, _) in H.in_edges([n])]
            children = [m for (_, m) in H.out_edges([n])]
            for k in parents:
                for m in children:
                    H.add_edge(k, m)
            H.remove_node(n)
        H.base_path = self.base_path
        return H

    def transitive_reduction(self) -> 'ImportGraph':
        """Removes all imports that are in the transitive closure of other imports."""
        H = self.edge_subgraph(nx.transitive_reduction(self).edges())
        H.base_path = self.base_path
        return H

    def delete_ported(self) -> 'ImportGraph':
        """Delete all nodes marked as ported during port_status"""
        H = self.subgraph({node for node, attrs in self.nodes(data=True)
                          if not (attrs.get("status") and attrs.get("status").ported)})
        H.base_path = self.base_path
        return H

    def delete_ported_children(self, exclude_tactics: bool) -> 'ImportGraph':
        """Delete all nodes marked as ported during port_status"""
        if exclude_tactics:
            to_remove = {n for n in self.nodes if str.startswith(n, ('tactic.', 'meta.'))}
        else:
            to_remove = set()
        finished_nodes = {node for node, attrs in self.nodes(data=True)
                          if attrs.get("status").ported}
        for node in finished_nodes:
            children = {child for _, child in self.out_edges(node)}
            if children.issubset(finished_nodes):
                to_remove.add(node)
        H = self.subgraph(self.nodes - to_remove)
        H.base_path = self.base_path
        return H

    def size(self) -> 'int':
        return nx.number_of_nodes(self)

    def longest_path_length(self) -> 'int':
        return nx.dag_longest_path_length(self)

    def longest_path(self):
        return nx.dag_longest_path(self)
