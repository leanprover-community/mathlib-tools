from pathlib import Path
from typing import Optional
import tempfile
import subprocess

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

    def to_gexf(self, path: Optional[Path] = None) -> None:
        """Writes itself to a gexf dot file, suitable for Gephi."""
        path = path or self.base_path/'import_graph.gexf'
        nx.write_gexf(self, str(path))

    def to_graphml(self, path: Optional[Path] = None) -> None:
        """Writes itself to a gexf dot file, suitable for yEd."""
        path = path or self.base_path/'import_graph.graphml'
        nx.write_graphml(self, str(path))

    def write(self, path: Path):
        if path.suffix == '.dot':
            self.to_dot(path)
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
                             'Use .dot, .gexf, .graphml or a valid '
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
