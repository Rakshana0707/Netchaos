import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { api } from '../api';

export function MonitoringDashboard({ networkId, nodes = [], onClose, inline = false }) {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [recovery, setRecovery] = useState(null);
  const [recoveryEvents, setRecoveryEvents] = useState([]);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const nameOf = (id) => {
    if (!id) return id;
    const found = nodes?.find(n => n.id === id);
    return found?.name || id;
  };
  
  const refresh = async () => {
    if (!networkId) return;
    try {
      const cur = await api.getMonitoringCurrent(networkId);
      let hist = await api.getMonitoringHistory(networkId);
      if (!hist || hist.length === 0) {
        await api.createMonitoringSnapshot(networkId).catch(() => null);
        hist = await api.getMonitoringHistory(networkId);
      }
      const [recSummary, recHistory] = await Promise.all([
        api.getRecoverySummary(networkId).catch(() => null),
        api.getRecoveryHistory(networkId).catch(() => [])
      ]);
      setCurrent(cur);
      // Reverse historical data for left-to-right timeline representation
      setHistory([...hist].reverse());
      setRecovery(recSummary);
      setRecoveryEvents(recHistory || []);
    } catch(err) {
      console.warn("Failed to refresh monitoring:", err);
    }
  };
  
  const forceSnapshot = async () => {
    await api.createMonitoringSnapshot(networkId);
    await refresh();
  };

  useEffect(() => {
    refresh();
    let interval;
    if (autoRefresh) {
      interval = setInterval(async () => {
        if (!networkId) return;
        await api.createMonitoringSnapshot(networkId).catch(() => null);
        refresh();
      }, 4000);
    }
    return () => clearInterval(interval);
  }, [networkId, autoRefresh]);

  if (!current) return <div className={`monitoring-overlay ${inline ? 'inline' : ''}`}><div className="monitoring-card">Loading Monitoring Metrics...</div></div>;

  const paddedHistory = history.length === 1 ? [
    { ...history[0], timestamp: new Date(new Date(history[0].timestamp).getTime() - 2000).toISOString() },
    history[0]
  ] : history;

  const chartData = paddedHistory.map(h => ({
    time: new Date(h.timestamp).toLocaleTimeString(),
    latency: h.traffic?.average_latency ?? 0,
    packetLoss: h.traffic?.packet_loss_percentage ?? 0,
    throughput: h.traffic?.throughput ?? 0,
    availability: h.connectivity?.traffic_availability ?? 100
  }));

  return (
    <div className={`monitoring-overlay ${inline ? 'inline' : ''}`}>
      <div className="monitoring-header">
        <h2>Network Monitoring & Performance</h2>
        <div className="monitoring-actions">
          <label style={{ marginRight: '15px' }}>
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} /> Auto-Refresh
          </label>
          <button className="button" onClick={forceSnapshot}>Manual Snapshot</button>
          {!inline && onClose && <button className="button" onClick={onClose} style={{ marginLeft: '10px' }}>Close</button>}
        </div>
      </div>

      <div className="monitoring-dashboard-grid">
        <div className="monitoring-card">
          <h3>Health Status</h3>
          <h1 className={`status-${current.health_status.toLowerCase()}`}>{current.health_status}</h1>
          <div className="stats-row">
            <div>Nodes: <b>{current.nodes.total}</b> <span>({current.nodes.active} active, {current.nodes.failed} failed)</span></div>
            <div>Links: <b>{current.links.total}</b> <span>({current.links.active} active, {current.links.failed} failed)</span></div>
            <div>Partitions: <b>{current.connectivity.partitions}</b></div>
          </div>
        </div>

        <div className="monitoring-card">
          <h3>Traffic Performance</h3>
          <div className="stats-row">
            <div>Latency: <b>{current.traffic.average_latency} ms</b></div>
            <div>Packet Loss: <b>{current.traffic.packet_loss_percentage}%</b></div>
            <div>Throughput: <b>{current.traffic.throughput} Mbps</b></div>
            <div>Availability: <b>{current.connectivity.traffic_availability}%</b></div>
          </div>
        </div>

        <div className="monitoring-card">
          <h3>Recovery Analysis</h3>
          {recovery && (
            <div className="stats-row">
              <div>Successful: <b>{recovery.successful_recoveries}/{recovery.total_recovery_events}</b></div>
              <div>Avg Time: <b>{recovery.average_recovery_time ? `${(recovery.average_recovery_time * 1000).toFixed(1)} ms` : "0 ms"}</b></div>
              <div>Restored: <b>{recovery.connectivity_restored_percentage}%</b></div>
            </div>
          )}
        </div>
      </div>

      {/* Rerouted Traffic Flows & Recovery Telemetry Section */}
      <div className="monitoring-card" style={{ marginTop: "12px", padding: "12px 16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <h3 style={{ margin: 0, fontSize: "14px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Dynamic Flow Recovery Telemetry
          </h3>
          {recoveryEvents.length > 0 ? (
            <span style={{ fontSize: "12px", background: "rgba(16, 185, 129, 0.15)", color: "var(--server)", padding: "2px 8px", borderRadius: "12px", fontWeight: "bold" }}>
              ✓ {recoveryEvents.filter(r => r.recovery_status === "RECOVERED" || r.status === "RECOVERED").length} Active Rerouted Flow(s)
            </span>
          ) : (
            <span style={{ fontSize: "11px", color: "var(--muted)" }}>No recovery events yet</span>
          )}
        </div>
        
        {recoveryEvents.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: "12px", padding: "8px 0" }}>
            Disrupted traffic flows recovered in the <b>Recovery</b> tab will stream live telemetry, route changes, and post-recovery latency metrics here.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "150px", overflowY: "auto" }}>
            {recoveryEvents.map((ev) => {
              const status = ev.recovery_status || ev.status || "UNKNOWN";
              const isRecovered = status === "RECOVERED";
              const origPath = ev.original_route?.map(nameOf).join(" → ") || "Original";
              const recPath = ev.recovered_route?.map(nameOf).join(" → ") || "None";
              return (
                <div 
                  key={ev.id || ev.recovery_id || Math.random()} 
                  style={{ 
                    display: "flex", 
                    justifyContent: "space-between", 
                    alignItems: "center", 
                    padding: "6px 10px", 
                    background: "var(--bg)", 
                    border: "1px solid var(--border)", 
                    borderRadius: "4px", 
                    fontSize: "12px" 
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: "bold" }}>{ev.simulation_id}</span>
                      <span style={{ color: "var(--muted)", textDecoration: "line-through", fontSize: "11px" }}>{origPath}</span>
                      <span style={{ color: "var(--server)", fontWeight: "bold" }}>➔ {recPath}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                    {ev.recovered_latency !== undefined && (
                      <span style={{ color: "var(--muted)" }}>Latency: <b style={{ color: "var(--text)" }}>{Number(ev.recovered_latency).toFixed(1)} ms</b></span>
                    )}
                    {ev.recovery_duration !== undefined && (
                      <span style={{ color: "var(--muted)" }}>Duration: <b style={{ color: "var(--text)" }}>{(ev.recovery_duration * 1000).toFixed(1)} ms</b></span>
                    )}
                    <span style={{ 
                      fontSize: "11px", 
                      fontWeight: "bold", 
                      color: isRecovered ? "var(--server)" : "var(--danger)",
                      padding: "2px 6px",
                      background: isRecovered ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
                      borderRadius: "4px"
                    }}>
                      {status}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      
      <div className="monitoring-charts" style={{ marginTop: "14px" }}>
        <div className="chart-box">
          <h4>Latency over Time (ms)</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="latency" stroke="#8884d8" name="Latency (ms)" dot={{ r: 4 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-box">
          <h4>Packet Loss (%)</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="packetLoss" stroke="#82ca9d" name="Packet Loss (%)" dot={{ r: 4 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-box">
          <h4>Throughput (Mbps)</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="throughput" stroke="#ffc658" name="Throughput (Mbps)" dot={{ r: 4 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
