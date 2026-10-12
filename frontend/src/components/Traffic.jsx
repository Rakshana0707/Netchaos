import { useState } from "react";

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const num = (value, digits = 2) => (value == null ? "—" : `${+Number(value).toFixed(digits)}`);

// Sidebar form: create a simulation, then run the selected (pending) one.
export function TrafficPanel({ nodes, disabled, selectedSim, onCreate, onRun }) {
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [packetCount, setPacketCount] = useState("100");
  const [packetSize, setPacketSize] = useState("1024");
  const [seed, setSeed] = useState("42");

  const count = Number(packetCount);
  const size = Number(packetSize);
  const sameNode = source !== "" && source === destination;
  const valid =
    source && destination && !sameNode &&
    Number.isInteger(count) && count > 0 && Number.isInteger(size) && size > 0 &&
    (seed === "" || (Number.isInteger(Number(seed)) && Number(seed) >= 0));

  const submit = (event) => {
    event.preventDefault();
    onCreate({
      source, destination, packet_count: count, packet_size: size,
      random_seed: seed === "" ? undefined : Number(seed), // blank: the server picks (and stores) one
    });
  };
  const options = nodes.map((n) => <option key={n.id} value={n.id}>{n.name}</option>);
  const canRun = !disabled && selectedSim?.status === "pending";

  return (
    <section className="panel">
      <h2>Traffic Simulation</h2>
      <form onSubmit={submit}>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)} disabled={disabled}>
            <option value="">Select node…</option>
            {options}
          </select>
        </label>
        <label>
          Destination
          <select value={destination} onChange={(e) => setDestination(e.target.value)} disabled={disabled}>
            <option value="">Select node…</option>
            {options}
          </select>
        </label>
        <div className="row">
          <label>
            Packet Count
            <input type="number" min="1" step="1" value={packetCount} onChange={(e) => setPacketCount(e.target.value)} disabled={disabled} />
          </label>
          <label>
            Packet Size (bytes)
            <input type="number" min="1" step="1" value={packetSize} onChange={(e) => setPacketSize(e.target.value)} disabled={disabled} />
          </label>
        </div>
        <label>
          Random Seed
          <input type="number" min="0" step="1" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="blank = generate" disabled={disabled} />
        </label>
        <button type="submit" disabled={disabled || !valid}>Create Simulation</button>
        <button type="button" className="secondary" disabled={!canRun} onClick={onRun}>
          Run Simulation{selectedSim ? ` (${selectedSim.simulation_id})` : ""}
        </button>
        {nodes.length >= 2 && (
          <button 
            type="button" 
            className="secondary" 
            disabled={disabled}
            style={{ marginTop: '4px', borderColor: 'var(--accent)', color: '#c4b5fd' }}
            onClick={() => {
              onCreate({
                source: nodes[0].id,
                destination: nodes[nodes.length - 1].id,
                packet_count: 500,
                packet_size: 1500,
                random_seed: 42
              });
            }}
          >
            ⚡ Quick Simulation ({nodes[0].name} ➔ {nodes[nodes.length - 1].name})
          </button>
        )}
      </form>
      <p className="hint">
        {sameNode
          ? "Source and destination must be different."
          : "Create adds a pending simulation; Run executes the selected pending one on the current topology."}
      </p>
    </section>
  );
}

// Bottom area: result of the selected simulation and the history of all simulations.
export function TrafficResults({ simulations, selectedId, metrics, nameOf, onSelect, children }) {
  const sim = simulations.find((s) => s.simulation_id === selectedId);
  const detail = metrics && metrics.simulation_id === selectedId ? metrics : null;
  const lossOf = (s) => (s.packet_loss_percentage == null ? "—" : `${num(s.packet_loss_percentage)}%`);
  const latencyOf = (s) => (s.path_latency_ms == null ? "—" : `${num(s.path_latency_ms)} ms`);

  return (
    <div className="results">
      <section className="panel">
        <h2>Traffic Result</h2>
        {!sim && <p className="hint">Create and run a simulation to see its result.</p>}
        {sim && (
          <>
            {sim.route && (
              <div style={{ marginBottom: "12px" }}>
                <div className="route-line" style={{ fontWeight: 600 }}>
                  <span className="swatch" />
                  Route: {sim.route.map(nameOf).join(" → ")}
                </div>
                <div className="hop-flow">
                  {sim.route.map((nodeId, idx) => (
                    <span key={nodeId} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                      <span className="hop-node">
                        <span style={{ color: '#38bdf8' }}>●</span>
                        {nameOf(nodeId)}
                      </span>
                      {idx < sim.route.length - 1 && <span className="hop-arrow">➔</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <dl className="compact">
              <dt>Simulation</dt><dd>{sim.simulation_id} <span className={`badge ${sim.status}`}>{sim.status}</span></dd>
              <dt>Seed</dt><dd>{sim.random_seed}</dd>
              <dt>Source</dt><dd>{nameOf(sim.source)}</dd>
              <dt>Destination</dt><dd>{nameOf(sim.destination)}</dd>
              <dt>Packets</dt><dd>{sim.packet_count} × {sim.packet_size} B</dd>
              {sim.status === "completed" && (
                <>
                  <dt>Delivered</dt><dd>{sim.delivered_packets}</dd>
                  <dt>Dropped</dt><dd>{sim.dropped_packets}</dd>
                  <dt>Packet Loss</dt><dd>{lossOf(sim)}</dd>
                  <dt>Latency</dt><dd>{latencyOf(sim)}</dd>
                  <dt>Hop Count</dt><dd>{sim.hop_count}</dd>
                  <dt>Path Bandwidth</dt><dd>{num(sim.path_bandwidth_mbps)} Mbps</dd>
                  <dt>Throughput</dt><dd>{num(sim.throughput_mbps)} Mbps</dd>
                  <dt>Data Delivered</dt><dd>{detail ? `${detail.total_data_transferred_bytes.toLocaleString()} B` : "…"}</dd>
                  <dt>Simulated Time</dt><dd>{num(sim.simulated_duration_ms)} ms</dd>
                  <dt>Execution Time</dt><dd>{num(sim.execution_duration_ms)} ms</dd>
                </>
              )}
            </dl>
            {sim.status === "failed" && <p className="reason">{sim.failure_reason}</p>}
            {sim.status === "pending" && <p className="hint">Not run yet.</p>}
          </>
        )}
      </section>

      <section className="panel">
        <h2>Simulation History</h2>
        {simulations.length === 0 ? (
          <p className="hint">No simulations yet.</p>
        ) : (
          <table className="history">
            <thead>
              <tr><th>ID</th><th>Source</th><th>Destination</th><th>Packets</th><th>Loss</th><th>Latency</th><th>Status</th></tr>
            </thead>
            <tbody>
              {simulations.map((s) => (
                <tr
                  key={s.simulation_id}
                  className={`pick${s.simulation_id === selectedId ? " is-picked" : ""}`}
                  onClick={() => onSelect(s.simulation_id)}
                >
                  <td>{s.simulation_id}</td>
                  <td>{nameOf(s.source)}</td>
                  <td>{nameOf(s.destination)}</td>
                  <td>{s.packet_count}</td>
                  <td>{lossOf(s)}</td>
                  <td>{latencyOf(s)}</td>
                  <td><span className={`badge ${s.status}`}>{capitalize(s.status)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {children}
    </div>
  );
}
