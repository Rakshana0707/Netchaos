import { useState, useEffect } from "react";
import { api } from "../api";

const capitalize = (text) => text && text.charAt(0).toUpperCase() + text.slice(1);
const num = (value, digits = 2) => (value == null ? "—" : `${+Number(value).toFixed(digits)}`);

export default function RecoveryPanel({ networkId, simulations, selectedSimId, nameOf, onRecovered }) {
  const [strategy, setStrategy] = useState("lowest_latency");
  const [previewData, setPreviewData] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState(null);
  const [recentRecovery, setRecentRecovery] = useState(null);

  // Clear preview when simulation changes
  useEffect(() => {
    setPreviewData(null);
    setRecentRecovery(null);
    setError(null);
  }, [selectedSimId]);

  const sim = simulations.find((s) => s.simulation_id === selectedSimId);

  const handlePreview = async () => {
    if (!sim) return;
    setExecuting(true);
    setError(null);
    try {
      const data = await api.previewRecovery(networkId, sim.simulation_id, strategy);
      setPreviewData(data);
      setRecentRecovery(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setExecuting(false);
    }
  };

  const handleRecover = async () => {
    if (!sim) return;
    setExecuting(true);
    setError(null);
    try {
      const data = await api.recoverSimulation(networkId, sim.simulation_id, strategy);
      setRecentRecovery(data);
      setPreviewData(null);
      if (onRecovered) onRecovered(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setExecuting(false);
    }
  };

  if (!sim) {
    return (
      <section className="panel recovery">
        <h2>Dynamic Recovery</h2>
        <p className="hint">Select a completed simulation to run recovery.</p>
      </section>
    );
  }

  const result = recentRecovery || previewData;
  const isPreview = !!previewData && !recentRecovery;

  return (
    <section className="panel recovery">
      <h2>Dynamic Recovery</h2>
      
      {error && <div style={{ color: "var(--danger)", fontSize: "13px", marginBottom: "8px" }}>{error}</div>}

      <dl className="compact" style={{ marginBottom: "12px" }}>
        <dt>Traffic</dt>
        <dd>{sim.simulation_id} ({nameOf(sim.source)} → {nameOf(sim.destination)})</dd>
      </dl>

      <div style={{ display: "flex", gap: "8px", flexDirection: "column", marginBottom: "12px" }}>
        <label>
          Recovery Strategy
          <select value={strategy} onChange={(e) => setStrategy(e.target.value)} disabled={executing}>
            <option value="lowest_latency">Lowest Latency</option>
            <option value="shortest_hop">Shortest Hop</option>
            <option value="highest_bandwidth">Highest Bandwidth</option>
            <option value="composite">Composite</option>
          </select>
        </label>

        <div style={{ display: "flex", gap: "8px" }}>
          <button type="button" className="secondary" onClick={handlePreview} disabled={executing || sim.status !== "completed"}>
            Preview Route
          </button>
          <button type="button" onClick={handleRecover} disabled={executing || sim.status !== "completed"} style={{ flex: 1 }}>
            Recover Traffic
          </button>
        </div>
      </div>

      {result && (
        <div style={{ marginTop: "16px", padding: "8px", borderTop: "1px solid var(--border)" }}>
          <h3 style={{ margin: "0 0 8px", fontSize: "14px" }}>
            {isPreview ? "Preview Result" : "Recovery Result"}
            <span style={{ float: "right", fontSize: "12px", color: result.status === "RECOVERED" ? "var(--server)" : "var(--danger)" }}>
              {result.status} {result.status === "RECOVERED" ? "✓" : ""}
            </span>
          </h3>

          {result.route_changed ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "13px" }}>
              <div>
                <strong>Original Route:</strong>
                <div style={{ color: "var(--muted)", margin: "4px 0" }}>
                  {result.original_route ? result.original_route.map(nameOf).join(" → ") : "None"}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "12px" }}>
                  <span>Lat: {num(result.original_latency)} ms</span>
                  <span>Hops: {result.original_hop_count}</span>
                  <span>BW: {num(result.original_bandwidth)} Mbps</span>
                </div>
              </div>

              <div>
                <strong>Recovered Route:</strong>
                <div style={{ color: "var(--route)", fontWeight: "bold", margin: "4px 0" }}>
                  {result.recovered_route ? result.recovered_route.map(nameOf).join(" → ") : "None"}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "12px" }}>
                  <span>Lat: {num(result.recovered_latency)} ms</span>
                  <span>Hops: {result.recovered_hop_count}</span>
                  <span>BW: {num(result.recovered_bandwidth)} Mbps</span>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: "13px" }}>
              <p>No route change. {result.failure_description || "Original route is still valid."}</p>
            </div>
          )}

          <div style={{ marginTop: "10px", fontSize: "12px", color: "var(--muted)" }}>
            Time: {num(result.recovery_duration * 1000, 2)} ms
            {result.connectivity_restored && <span style={{ marginLeft: "10px", color: "var(--server)" }}>• Connectivity Restored</span>}
          </div>
        </div>
      )}
    </section>
  );
}
