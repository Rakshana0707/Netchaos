import { useCallback, useEffect, useMemo, useState } from "react";
import { Background, Controls, Handle, Position, ReactFlow } from "@xyflow/react";

// One visual style per device type (see styles.css).
const GLYPHS = { router: "⇄", host: "▣", server: "▤", client: "▭", switch: "⇋", endpoint: "💻" };

function DeviceNode({ data, selected }) {
  return (
    <div
      className={`device device-${data.type}${selected ? " is-selected" : ""}${data.onRoute ? " on-route" : ""}${data.failed ? " is-failed" : ""}`}
      title={data.failed ? `${data.label} has FAILED` : `${data.label} (${data.type})`}
    >
      <span className={`device-beacon ${data.failed ? 'failed' : data.onRoute ? 'route' : 'active'}`} />
      {data.failed && <span className="device-x" aria-label="failed">✕</span>}
      {/* Handles sit in the centre so links run centre-to-centre. */}
      <Handle type="target" position={Position.Top} className="handle" isConnectable={false} />
      <Handle type="source" position={Position.Bottom} className="handle" isConnectable={false} />
      <span className="device-glyph">{GLYPHS[data.type]}</span>
      <span className="device-name">{data.label}</span>
      <span className="device-type">{data.failed ? "FAILED" : data.type}</span>
    </div>
  );
}

const nodeTypes = { device: DeviceNode };

// Nodes start on a circle; dragging a node overrides its position.
function circleLayout(nodes) {
  const radius = Math.max(120, nodes.length * 32);
  return Object.fromEntries(
    nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1) - Math.PI / 2;
      return [node.id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }];
    })
  );
}

// `route` is an optional list of node ids; the links between consecutive nodes are drawn as the active route.
// Link scenarios that leave the link up but change how it behaves.
const DEGRADING = new Set(["packet_loss", "latency", "bandwidth_reduction", "congestion"]);

// `chaos` is the list of active experiments (from /chaos/active); it tells us which links are degraded.
export default function TopologyCanvas({ topology, selection, onSelect, resetKey, route = null, chaos = [] }) {
  const [dragged, setDragged] = useState({});
  useEffect(() => setDragged({}), [resetKey]);

  const layout = useMemo(() => circleLayout(topology.nodes), [topology.nodes]);

  const routeNodes = useMemo(() => new Set(route ?? []), [route]);
  const routeLinks = useMemo(() => {
    const keys = new Set();
    (route ?? []).slice(1).forEach((node, i) => keys.add([route[i], node].sort().join("|")));
    return keys;
  }, [route]);

  const failedNodes = useMemo(
    () => new Set(topology.nodes.filter((n) => n.status !== "active").map((n) => n.id)),
    [topology.nodes]
  );
  const degradedLinks = useMemo(
    () => new Set(chaos.flatMap((exp) => exp.events).filter((e) => DEGRADING.has(e.scenario)).map((e) => e.target_id)),
    [chaos]
  );

  const nodes = useMemo(
    () =>
      topology.nodes.map((node) => ({
        id: node.id,
        type: "device",
        position: dragged[node.id] ?? layout[node.id],
        data: { label: node.name, type: node.type, onRoute: routeNodes.has(node.id), failed: failedNodes.has(node.id) },
        selected: selection?.kind === "node" && selection.id === node.id,
      })),
    [topology.nodes, layout, dragged, selection, routeNodes, failedNodes]
  );

  const edges = useMemo(
    () =>
      topology.links.map((link) => {
        const onRoute = routeLinks.has([link.source, link.destination].sort().join("|"));
        const failed = link.status !== "active";
        const blocked = !failed && (failedNodes.has(link.source) || failedNodes.has(link.destination));
        const degraded = !failed && !blocked && degradedLinks.has(link.id);
        const values = `${link.bandwidth} Mbps · ${link.latency} ms · ${link.packet_loss}% loss`;
        let label = `${link.bandwidth} Mbps · ${link.latency} ms`;
        if (failed) label = "✕ FAILED";
        else if (blocked) label = "unavailable (router down)";
        else if (degraded) label = values;
        const classes = [
          onRoute && "on-route", failed && "link-failed", blocked && "link-blocked", degraded && "link-degraded",
        ].filter(Boolean);
        
        // Dynamic edge styling
        const edgeStyle = onRoute 
          ? { stroke: "#38bdf8", strokeWidth: 4, filter: "drop-shadow(0 0 6px rgba(56, 189, 248, 0.9))" }
          : failed
          ? { stroke: "#ef4444", strokeWidth: 3, strokeDasharray: "6 6" }
          : blocked
          ? { stroke: "#64748b", strokeWidth: 2, strokeDasharray: "4 4" }
          : degraded
          ? { stroke: "#f59e0b", strokeWidth: 3, strokeDasharray: "6 4" }
          : { stroke: "rgba(255, 255, 255, 0.25)", strokeWidth: 2 };

        return {
          id: link.id,
          source: link.source,
          target: link.destination,
          type: "straight",
          label,
          className: classes.join(" "),
          animated: Boolean(onRoute || degraded),
          style: edgeStyle,
          zIndex: onRoute || failed || degraded ? 10 : 0,
          selected: selection?.kind === "link" && selection.id === link.id,
          interactionWidth: 24,
        };
      }),
    [topology.links, selection, routeLinks, failedNodes, degradedLinks]
  );

  const onNodesChange = useCallback((changes) => {
    setDragged((prev) => {
      let next = prev;
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          if (next === prev) next = { ...prev };
          next[change.id] = change.position;
        }
      }
      return next;
    });
  }, []);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, node) => onSelect({ kind: "node", id: node.id })}
      onEdgeClick={(_, edge) => onSelect({ kind: "link", id: edge.id })}
      onPaneClick={() => onSelect(null)}
      nodesConnectable={false}
      elementsSelectable
      fitView
      fitViewOptions={{ padding: 0.3 }}
      key={`${resetKey}-${topology.nodes.length}`}
      minZoom={0.2}
    >
      <Background gap={20} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
