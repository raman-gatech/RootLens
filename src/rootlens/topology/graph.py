"""NetworkX-backed deterministic service graph traversal."""

import networkx as nx

from rootlens.topology.contracts import ServiceGraphSnapshot, ServicePath, ServiceSet
from rootlens.topology.errors import ServiceNotFoundError, ServicePathNotFoundError


class ServiceGraph:
    """Traverse dependencies in caller-to-callee direction."""

    def __init__(self, snapshot: ServiceGraphSnapshot) -> None:
        self.snapshot = snapshot
        self._graph: nx.DiGraph[str] = nx.DiGraph()
        for node in snapshot.nodes:
            self._graph.add_node(node.service, evidence=node)
        for edge in snapshot.edges:
            self._graph.add_edge(edge.caller, edge.callee, evidence=edge)

    def direct_dependencies(self, service: str) -> ServiceSet:
        self._require_service(service)
        return ServiceSet(service=service, services=tuple(sorted(self._graph.successors(service))))

    def dependencies(self, service: str) -> ServiceSet:
        self._require_service(service)
        return ServiceSet(
            service=service, services=tuple(sorted(nx.descendants(self._graph, service)))
        )

    def callers(self, service: str) -> ServiceSet:
        self._require_service(service)
        return ServiceSet(
            service=service, services=tuple(sorted(nx.ancestors(self._graph, service)))
        )

    def shortest_dependency_path(self, source: str, target: str) -> ServicePath:
        self._require_service(source)
        self._require_service(target)
        try:
            path = nx.shortest_path(self._graph, source=source, target=target)
        except nx.NetworkXNoPath as exc:
            raise ServicePathNotFoundError(
                f"no dependency path from {source!r} to {target!r}"
            ) from exc
        return ServicePath(source=source, target=target, services=tuple(path))

    def _require_service(self, service: str) -> None:
        if service not in self._graph:
            raise ServiceNotFoundError(f"service {service!r} is absent from this graph snapshot")
