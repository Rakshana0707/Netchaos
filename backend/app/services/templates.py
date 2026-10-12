"""Pure functions that describe template topologies. They touch neither the database nor the graph."""
from dataclasses import dataclass
from itertools import combinations

from app.enums import NodeType
from app.schemas.topology import TemplateName

NodeSpec = tuple[str, NodeType]  # (name, type)
LinkSpec = tuple[int, int]  # indexes into the node list


@dataclass(frozen=True)
class TemplateSpec:
    default_count: int
    min_count: int
    max_count: int


SPECS: dict[TemplateName, TemplateSpec] = {
    TemplateName.LINEAR: TemplateSpec(4, 2, 50),
    TemplateName.STAR: TemplateSpec(5, 3, 50),
    TemplateName.RING: TemplateSpec(4, 3, 50),
    TemplateName.MESH: TemplateSpec(4, 2, 12),  # a mesh has n(n-1)/2 links
}


def _label(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


def _name(node_type: NodeType, index: int) -> str:
    return f"{node_type.value.capitalize()}-{_label(index)}"


def _routers(count: int) -> list[NodeSpec]:
    return [(_name(NodeType.ROUTER, i), NodeType.ROUTER) for i in range(count)]


def build_template(template: TemplateName, count: int) -> tuple[list[NodeSpec], list[LinkSpec]]:
    if template is TemplateName.LINEAR:
        # A client at one end, a server at the other, routers in between.
        types = [NodeType.CLIENT] + [NodeType.ROUTER] * (count - 2) + [NodeType.SERVER]
        nodes = [(_name(t, i), t) for i, t in enumerate(types)]
        links = [(i, i + 1) for i in range(count - 1)]
    elif template is TemplateName.STAR:
        hub = (_name(NodeType.ROUTER, 0), NodeType.ROUTER)
        nodes = [hub] + [(_name(NodeType.HOST, i), NodeType.HOST) for i in range(1, count)]
        links = [(0, i) for i in range(1, count)]
    elif template is TemplateName.RING:
        nodes = _routers(count)
        links = [(i, (i + 1) % count) for i in range(count)]
    else:  # mesh
        nodes = _routers(count)
        links = list(combinations(range(count), 2))
    return nodes, links
