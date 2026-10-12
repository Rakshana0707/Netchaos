from app.graph.graph_manager import GraphError, GraphManager

# One shared manager for the whole process: later modules import this same instance.
graph_manager = GraphManager()

__all__ = ["GraphError", "GraphManager", "graph_manager"]
