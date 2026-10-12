import { useState } from "react";

const NODE_TYPES = ["router", "host", "server", "client", "switch", "endpoint"];
const TEMPLATES = ["linear", "star", "ring", "mesh"];
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

export function NetworkPanel({ networks, networkId, onSelect, onCreate }) {
  const [name, setName] = useState("");
  const submit = (event) => {
    event.preventDefault();
    onCreate(name.trim()).then((created) => created && setName(""));
  };
  return (
    <section className="panel">
      <h2>Network</h2>
      {networks.length > 0 && (
        <label>
          Open network
          <select value={networkId || ""} onChange={(e) => onSelect(e.target.value)}>
            {networks.map((n) => (
              <option key={n.network_id} value={n.network_id}>
                {n.name} ({n.network_id})
              </option>
            ))}
          </select>
        </label>
      )}
      <form onSubmit={submit}>
        <label>
          Network Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Campus Network" />
        </label>
        <button type="submit" disabled={!name.trim()}>Create Network</button>
      </form>
    </section>
  );
}

export function NodeForm({ disabled, onAdd }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("router");
  const submit = (event) => {
    event.preventDefault();
    onAdd({ name: name.trim(), type }).then((added) => added && setName(""));
  };
  return (
    <section className="panel">
      <h2>Add Node</h2>
      <form onSubmit={submit}>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Router-A" disabled={disabled} />
        </label>
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value)} disabled={disabled}>
            {NODE_TYPES.map((t) => (
              <option key={t} value={t}>{capitalize(t)}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={disabled || !name.trim()}>Add Node</button>
      </form>
    </section>
  );
}

export function LinkForm({ nodes, disabled, onAdd }) {
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [bandwidth, setBandwidth] = useState("100");
  const [latency, setLatency] = useState("10");
  const [packetLoss, setPacketLoss] = useState("0");

  const submit = (event) => {
    event.preventDefault();
    onAdd({
      source,
      destination,
      bandwidth: Number(bandwidth),
      latency: Number(latency),
      packet_loss: Number(packetLoss),
    });
  };
  const nodeOptions = nodes.map((n) => (
    <option key={n.id} value={n.id}>{n.name}</option>
  ));
  const ready = source && destination && bandwidth !== "" && latency !== "" && packetLoss !== "";
  return (
    <section className="panel">
      <h2>Add Link</h2>
      <form onSubmit={submit}>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)} disabled={disabled}>
            <option value="">Select node…</option>
            {nodeOptions}
          </select>
        </label>
        <label>
          Destination
          <select value={destination} onChange={(e) => setDestination(e.target.value)} disabled={disabled}>
            <option value="">Select node…</option>
            {nodeOptions}
          </select>
        </label>
        <div className="row">
          <label>
            Bandwidth (Mbps)
            <input type="number" min="0" step="any" value={bandwidth} onChange={(e) => setBandwidth(e.target.value)} />
          </label>
          <label>
            Latency (ms)
            <input type="number" min="0" step="any" value={latency} onChange={(e) => setLatency(e.target.value)} />
          </label>
          <label>
            Loss (%)
            <input type="number" min="0" max="100" step="any" value={packetLoss} onChange={(e) => setPacketLoss(e.target.value)} />
          </label>
        </div>
        <button type="submit" disabled={disabled || !ready}>Create Link</button>
      </form>
    </section>
  );
}

export function TemplatePanel({ disabled, isEmpty, onApply }) {
  return (
    <section className="panel">
      <h2>Templates</h2>
      <div className="row">
        {TEMPLATES.map((t) => (
          <button key={t} type="button" className="secondary" disabled={disabled || !isEmpty} onClick={() => onApply(t)}>
            {capitalize(t)}
          </button>
        ))}
      </div>
      <p className="hint">{isEmpty ? "Generates nodes and links in this network." : "Templates need an empty network."}</p>
    </section>
  );
}

export function DetailsPanel({ selection, topology, onDeleteNode, onDeleteLink }) {
  if (!selection) {
    return (
      <section className="panel">
        <h2>Details</h2>
        <p className="hint">Click a node or link to see its properties.</p>
      </section>
    );
  }
  if (selection.kind === "node") {
    const node = topology.nodes.find((n) => n.id === selection.id);
    if (!node) return null;
    return (
      <section className="panel">
        <h2>Node</h2>
        <dl>
          <dt>Name</dt><dd>{node.name}</dd>
          <dt>Type</dt><dd>{capitalize(node.type)}</dd>
          <dt>Status</dt><dd>{capitalize(node.status)}</dd>
          <dt>ID</dt><dd>{node.id}</dd>
        </dl>
        <button type="button" className="danger" onClick={() => onDeleteNode(node)}>Delete node</button>
      </section>
    );
  }
  const link = topology.links.find((l) => l.id === selection.id);
  if (!link) return null;
  const nameOf = (id) => topology.nodes.find((n) => n.id === id)?.name ?? id;
  return (
    <section className="panel">
      <h2>Link</h2>
      <dl>
        <dt>Connects</dt><dd>{nameOf(link.source)} ↔ {nameOf(link.destination)}</dd>
        <dt>Bandwidth</dt><dd>{link.bandwidth} Mbps</dd>
        <dt>Latency</dt><dd>{link.latency} ms</dd>
        <dt>Packet Loss</dt><dd>{link.packet_loss}%</dd>
        <dt>Status</dt><dd>{capitalize(link.status)}</dd>
        <dt>ID</dt><dd>{link.id}</dd>
      </dl>
      <button type="button" className="danger" onClick={() => onDeleteLink(link)}>Delete link</button>
    </section>
  );
}
