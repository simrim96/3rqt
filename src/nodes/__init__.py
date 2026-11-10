"""Node registry: configurazione dei nodi e adapter OpenAI-compatibile.

Nessun nome di modello/runtime hardcodato qui (PLAN §0.2): tutto da YAML
(`config/nodes.yaml`).
"""

from nodes.client import NodeStatus, chat_completion, list_models, probe_node
from nodes.config import Node, NodesConfig, Policy, load_nodes_config

__all__ = [
    "Node",
    "NodesConfig",
    "NodeStatus",
    "Policy",
    "chat_completion",
    "list_models",
    "load_nodes_config",
    "probe_node",
]
