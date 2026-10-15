import { useState, useEffect } from "react";
import { api } from "../api";

const num = (value, digits = 2) => (value == null ? "—" : `${+Number(value).toFixed(digits)}`);

export default function RecoveryPanel({
  networkId,
  simulations = [],
  selectedSimId,
  onSelectSim,
  onPreviewRoute,
  nameOf,
  onRecovered,
}) {
  const [strategy, setStrategy] = useState("lowest_latency");
  const [previewData, setPreviewData] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState(null);
  const [recentRecovery, setRecentRecovery] = useState(null);
  const [history, setHistory] = useState([]);

  // Auto-select first completed simulation if none is selected
  useEffect(() => {
    if (!selectedSimId && simulations.length > 0) {
      const first = simulations.find((s) => s.status === "completed") || simulations[0];
      if (first && onSelectSim) {
        onSelectSim(first.simulation_id);
      }
    }
  }, [selectedSimId, simulations, onSelectSim]);

  // Load recovery history
  const loadHistory = async () => {
    if (!networkId) return;
    try {
      const h = await api.getRecoveryHistory(networkId);
      setHistory(h || []);
    } catch {
      // Ignore background history fetch errors
    }
  };

  useEffect(() => {
    loadHistory();
  }, [networkId]);

  // Clear preview when selected simulation changes
  useEffect(() => {
    setPreviewData(null);
    setRecentRecovery(null);
    setError(null);
    if (onPreviewRoute) onPreviewRoute(null);
  }, [selectedSimId]);

  const sim = simulations.find((s) => s.simulation_id === selectedSimId) || null;

  const handlePreview = async () => {
    if (!sim) return;
    setExecuting(true);
    setError(null);
    try {
      const data = await api.previewRecovery(networkId, sim.simulation_id, strategy);
      setPreviewData(data);
      setRecentRecovery(null);
      if (onPreviewRoute && data.recovered_route) {
        onPreviewRoute(data.recovered_route);
      }
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
      if (onPreviewRoute && data.recovered_route) {
        onPreviewRoute(data.recovered_route);
      }
      await loadHistory();
      if (onRecovered) onRecovered(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setExecuting(false);
    }
  };

  const handleRecoverAll = async () => {
    setExecuting(true);
    setError(null);
    try {
      const results = await api.recoverAll(networkId, strategy);
      const last = Array.isArray(results) && results.length > 0 ? results[results.length - 1] : null;
      if (last) {
        setRecentRecovery(last);
        setPreviewData(null);
        if (onPreviewRoute && last.recovered_route) {
          onPreviewRoute(last.recovered_route);
        }
      }
      await loadHistory();
      if (onRecovered) onRecovered(last);
    } catch (err) {
      setError(err.message);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <section className="panel recovery" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Dynamic Recovery</h2>
        <span style={{ fontSize: "11px", color: "var(--muted)" }}>Module 5</span>
      </div>

      {error && <div className="error-banner" style={{ color: "var(--danger)", fontSize: "12px", background: "rgba(239,68,68,0.1)", padding: "6px 8px", borderRadius: "4px" }}>{error}</div>}

      {/* Target Simulation Selection */}
      {simulations.length === 0 ? (
        <div style={{ padding: "12px", background: "var(--bg)", borderRadius: "6px", border: "1px solid var(--border)", fontSize: "13px" }}>
          <p style={{ margin: "0 0 8px", fontWeight: "600", color: "var(--muted)" }}>No Traffic Flows Found</p>
          <p style={{ margin: 0, color: "var(--muted)", fontSize: "12px", lineHeight: "1.4" }}>
            To demonstrate dynamic recovery:
            <br />1. Go to <b>Traffic</b> tab and run a simulation.
            <br />2. Go to <b>Chaos</b> tab and inject a failure on that path.
            <br />3. Return here to reroute traffic around the broken node/link!
          </p>
        </div>
      ) : (
        <div>
          <label style={{ fontSize: "12px", color: "var(--muted)", display: "block", marginBottom: "4px" }}>
            Target Traffic Simulation:
          </label>
          <select
            value={selectedSimId || ""}
            onChange={(e) => onSelectSim && onSelectSim(e.target.value)}
            disabled={executing}
            style={{ width: "100%", padding: "6px", fontSize: "13px", borderRadius: "4px" }}
          >
            {simulations.map((s) => (
              <option key={s.simulation_id} value={s.simulation_id}>
                {s.simulation_id} ({nameOf(s.source)} → {nameOf(s.destination)}) [{s.status}]
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Strategy and Action Controls */}
      {sim && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <label style={{ fontSize: "12px", color: "var(--muted)" }}>
            Recovery Algorithm:
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              disabled={executing}
              style={{ width: "100%", marginTop: "4px" }}
            >
              <option value="lowest_latency">Lowest Latency (Dijkstra weight)</option>
              <option value="shortest_hop">Shortest Hop (BFS)</option>
              <option value="highest_bandwidth">Highest Bandwidth (Max bottleneck)</option>
              <option value="composite">Composite Weighted (Balanced)</option>
            </select>
          </label>

          <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
            <button
              type="button"
              className="secondary"
              onClick={handlePreview}
              disabled={executing || sim.status !== "completed"}
              style={{ flex: 1 }}
              title="Calculate alternative route and project metrics without saving"
            >
              Preview Route
            </button>
            <button
              type="button"
              onClick={handleRecover}
              disabled={executing || sim.status !== "completed"}
              style={{ flex: 1.2, fontWeight: "bold" }}
              title="Apply new route to simulation and restore flow"
            >
              Recover Flow
            </button>
          </div>

          <button
            type="button"
            className="secondary"
            onClick={handleRecoverAll}
            disabled={executing}
            style={{ fontSize: "12px", padding: "4px 8px" }}
            title="Attempt recovery for all disrupted flows in network"
          >
            Recover All Disrupted Flows
          </button>
        </div>
      )}

      {/* Result Display */}
      {(recentRecovery || previewData) && (
        (() => {
          const result = recentRecovery || previewData;
          const isPreview = !!previewData && !recentRecovery;
          return (
            <div style={{ padding: "10px", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: "6px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                <span style={{ fontSize: "13px", fontWeight: "bold" }}>
                  {isPreview ? "Route Preview" : "Recovery Result"}
                </span>
                <span style={{ fontSize: "12px", fontWeight: "bold", color: result.status === "RECOVERED" ? "var(--server)" : "var(--danger)" }}>
                  {result.status} {result.status === "RECOVERED" ? "✓" : "✗"}
                </span>
              </div>

              {result.route_changed ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "12px" }}>
                  <div>
                    <span style={{ color: "var(--muted)" }}>Original Path:</span>
                    <div style={{ fontFamily: "monospace", margin: "2px 0" }}>
                      {result.original_route ? result.original_route.map(nameOf).join(" → ") : "None"}
                    </div>
                    <div style={{ display: "flex", gap: "10px", color: "var(--muted)" }}>
                      <span>Lat: {num(result.original_latency)} ms</span>
                      <span>Hops: {result.original_hop_count}</span>
                      <span>BW: {num(result.original_bandwidth)} Mbps</span>
                    </div>
                  </div>

                  <div style={{ borderTop: "1px dashed var(--border)", paddingTop: "6px" }}>
                    <span style={{ color: "var(--server)", fontWeight: "600" }}>Recovered Path:</span>
                    <div style={{ fontFamily: "monospace", color: "var(--server)", fontWeight: "bold", margin: "2px 0" }}>
                      {result.recovered_route ? result.recovered_route.map(nameOf).join(" → ") : "None"}
                    </div>
                    <div style={{ display: "flex", gap: "10px" }}>
                      <span>Lat: <b>{num(result.recovered_latency)} ms</b></span>
                      <span>Hops: <b>{result.recovered_hop_count}</b></span>
                      <span>BW: <b>{num(result.recovered_bandwidth)} Mbps</b></span>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                  {result.failure_description || "Original route is still operational; no alternate path needed."}
                </div>
              )}

              <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--muted)" }}>
                Compute Duration: {num(result.recovery_duration * 1000, 2)} ms
                {result.connectivity_restored && <span style={{ marginLeft: "8px", color: "var(--server)" }}>• Connectivity Restored</span>}
              </div>
            </div>
          );
        })()
      )}

      {/* Recovery History Log */}
      <div style={{ marginTop: "4px" }}>
        <div style={{ fontSize: "12px", fontWeight: "bold", color: "var(--muted)", textTransform: "uppercase", marginBottom: "6px" }}>
          Recovery History ({history.length})
        </div>
        <div className="scroll-list" style={{ maxHeight: "150px", overflowY: "auto", fontSize: "12px" }}>
          {history.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: "12px", fontStyle: "italic" }}>No recovery events logged yet.</div>
          ) : (
            history.map((h) => (
              <div key={h.recovery_id} style={{ padding: "6px 8px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
                <div>
                  <div><b>{h.simulation_id}</b></div>
                  <div style={{ fontSize: "11px", color: "var(--muted)" }}>
                    {h.recovered_route ? h.recovered_route.map(nameOf).join(" → ") : "No route"}
                  </div>
                </div>
                <span style={{ fontSize: "11px", fontWeight: "bold", color: h.status === "RECOVERED" ? "var(--server)" : "var(--danger)" }}>
                  {h.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
