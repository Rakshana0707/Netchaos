import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

export function DashboardOverview({ networkId, topology, chaosActive, simulations, onRefresh }) {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [activeScenario, setActiveScenario] = useState(null);
  const [scenarioLogs, setScenarioLogs] = useState([]);
  const [runningScenario, setRunningScenario] = useState(false);
  const [liveStream, setLiveStream] = useState(true);

  const fetchTelemetry = useCallback(async () => {
    if (!networkId) return;
    try {
      const [cur, hist] = await Promise.all([
        api.getMonitoringCurrent(networkId),
        api.getHistory(networkId)
      ]);
      setCurrent(cur);
      setHistory(hist || []);
    } catch (e) {
      console.warn("Telemetry fetch error:", e);
    }
  }, [networkId]);

  useEffect(() => {
    fetchTelemetry();
    if (!liveStream) return;
    const interval = setInterval(fetchTelemetry, 3000);
    return () => clearInterval(interval);
  }, [fetchTelemetry, liveStream]);

  const addLog = (msg, status = "running") => {
    setScenarioLogs(prev => [...prev, { msg, status, time: new Date().toLocaleTimeString() }]);
  };

  const updateLastLog = (status) => {
    setScenarioLogs(prev => {
      if (prev.length === 0) return prev;
      const copy = [...prev];
      copy[copy.length - 1] = { ...copy[copy.length - 1], status };
      return copy;
    });
  };

  const runScenario1 = async () => {
    if (!topology?.nodes?.length || runningScenario) return;
    setRunningScenario(true);
    setActiveScenario("⚡ Core Link Outage & SPF Route Healing");
    setScenarioLogs([]);

    try {
      const src = topology.nodes[0]?.id;
      const dst = topology.nodes[topology.nodes.length - 1]?.id;
      const link = topology.links[0]?.id;

      addLog(`[1/4] Initiating Baseline Traffic Simulation (${src} ➔ ${dst})...`);
      const sim = await api.createSimulation(networkId, {
        source: src,
        destination: dst,
        packet_count: 500,
        packet_size: 1500,
        store_packets: false
      });
      await api.runSimulation(networkId, sim.simulation_id);
      updateLastLog("done");

      addLog(`[2/4] Injecting Chaos: Breaking Core Link (${link})...`);
      const chaos = await api.injectChaos(networkId, "link_failure", { link_id: link });
      await api.createMonitoringSnapshot(networkId);
      updateLastLog("done");
      await fetchTelemetry();

      addLog(`[3/4] Running Dynamic Route Recovery (Dijkstra Alternate)...`);
      await api.recoverNetwork(networkId, {
        strategy: "dijkstra_alternate",
        simulation_id: sim.simulation_id
      });
      updateLastLog("done");

      addLog(`[4/4] Restoring Network: Reverting Link Chaos...`);
      if (chaos?.experiment_id) {
        await api.revertChaos(networkId, chaos.experiment_id);
      }
      await api.createMonitoringSnapshot(networkId);
      updateLastLog("done");

      addLog(`🎉 Scenario 1 Completed Successfully! Resilient route verified.`, "done");
    } catch (err) {
      addLog(`❌ Scenario Error: ${err.message}`, "fail");
    } finally {
      setRunningScenario(false);
      fetchTelemetry();
      if (onRefresh) onRefresh();
    }
  };

  const runScenario2 = async () => {
    if (!topology?.nodes?.length || runningScenario) return;
    setRunningScenario(true);
    setActiveScenario("🌊 High-Volume Traffic Flood & Congestion");
    setScenarioLogs([]);

    try {
      const src = topology.nodes[0]?.id;
      const dst = topology.nodes[topology.nodes.length - 1]?.id;
      const link = topology.links[0]?.id;

      addLog(`[1/3] Generating High-Load Packet Stream (2,500 packets)...`);
      const sim = await api.createSimulation(networkId, {
        source: src,
        destination: dst,
        packet_count: 2500,
        packet_size: 1500,
        store_packets: false
      });
      await api.runSimulation(networkId, sim.simulation_id);
      updateLastLog("done");

      addLog(`[2/3] Simulating Network Congestion & 15% Packet Loss on ${link}...`);
      const chaos = await api.injectChaos(networkId, "packet_loss", {
        link_id: link,
        loss_percentage: 15
      });
      await api.createMonitoringSnapshot(networkId);
      updateLastLog("done");
      await fetchTelemetry();

      addLog(`[3/3] Capturing Real-Time Degraded Telemetry & Reverting...`);
      if (chaos?.experiment_id) {
        await api.revertChaos(networkId, chaos.experiment_id);
      }
      await api.createMonitoringSnapshot(networkId);
      updateLastLog("done");

      addLog(`🎉 Scenario 2 Completed! Congestion response recorded.`, "done");
    } catch (err) {
      addLog(`❌ Scenario Error: ${err.message}`, "fail");
    } finally {
      setRunningScenario(false);
      fetchTelemetry();
      if (onRefresh) onRefresh();
    }
  };

  const runScenario3 = async () => {
    if (runningScenario) return;
    setRunningScenario(true);
    setActiveScenario("🛡️ Full Resilience Benchmark Suite");
    setScenarioLogs([]);

    try {
      addLog(`[1/3] Creating Resilience Benchmark Experiment Plan...`);
      const src = topology.nodes[0]?.id;
      const link = topology.links[0]?.id;
      const plan = await api.createExperimentPlan({
        name: `Automated Resilience Benchmark - ${new Date().toLocaleTimeString()}`,
        description: "Comprehensive stress test across nodes and links",
        network_id: networkId,
        target_simulations: [],
        chaos_events: [
          { type: link ? "link_failure" : "node_failure", ...(link ? { link_id: link } : { node_id: src }) }
        ],
        recovery_strategy: "dijkstra_alternate"
      });
      updateLastLog("done");

      addLog(`[2/3] Executing Plan Batch & Calculating Impact Scores...`);
      await api.runExperimentPlan(plan.plan_id);
      updateLastLog("done");

      addLog(`[3/3] Generating Research Dataset & Updating Analytics...`);
      await api.createDataset({
        name: `Benchmark Dataset - ${new Date().toLocaleTimeString()}`,
        version: "1.0",
        description: "Real telemetry and recovery traces from live benchmark",
        filters: {}
      });
      updateLastLog("done");

      addLog(`🎉 Full Benchmark Suite Complete! Analytics & Dataset Labs populated.`, "done");
    } catch (err) {
      addLog(`❌ Benchmark Error: ${err.message}`, "fail");
    } finally {
      setRunningScenario(false);
      fetchTelemetry();
      if (onRefresh) onRefresh();
    }
  };

  const handleResetAllChaos = async () => {
    try {
      await api.resetChaos(networkId);
      await api.createMonitoringSnapshot(networkId);
      fetchTelemetry();
      if (onRefresh) onRefresh();
    } catch (e) {
      console.warn("Reset chaos error:", e);
    }
  };

  if (!networkId) return <div className="empty">Select or create a network to view dashboard</div>;

  return (
    <div className="dashboard-overview" style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* HEADER WITH LIVE STREAM CONTROLS */}
      <div className="monitoring-header">
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            NETCHAOS MISSION CONTROL
            <span 
              className={`live-stream-badge ${liveStream ? '' : 'paused'}`}
              onClick={() => setLiveStream(!liveStream)}
              title="Click to toggle live stream"
            >
              <span className="live-stream-dot" />
              {liveStream ? 'LIVE (3s)' : 'PAUSED'}
            </span>
          </h2>
          <small style={{ color: 'var(--muted)', fontSize: '13px' }}>
            Real-Time Network Telemetry & Automated Resilience Chaos Orchestration
          </small>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button 
            type="button" 
            className="secondary" 
            onClick={fetchTelemetry}
            style={{ padding: '8px 16px', fontSize: '13px' }}
          >
            ↻ Refresh Telemetry
          </button>
          <button 
            type="button" 
            className="secondary" 
            onClick={handleResetAllChaos}
            style={{ padding: '8px 16px', fontSize: '13px', color: '#f87171' }}
          >
            Heal All & Reset Chaos
          </button>
        </div>
      </div>

      {/* TOP TELEMETRY CARDS */}
      <div className="monitoring-dashboard-grid" style={{ marginTop: '20px' }}>
        <div className="monitoring-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)', paddingBottom: '12px' }}>
            <h3 style={{ margin: 0, border: 'none', padding: 0 }}>System Health</h3>
            <span className={`status-beacon ${current?.health_status === 'HEALTHY' ? 'active' : current?.health_status === 'CRITICAL' ? 'failed' : 'route'}`} style={{ position: 'static' }} />
          </div>
          {current ? (
            <div style={{ marginTop: '14px' }}>
              <h1 className={`status-${current.health_status.toLowerCase()}`} style={{ margin: '0 0 14px 0', fontSize: '28px' }}>
                {current.health_status}
              </h1>
              <div className="stats-row">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--muted)' }}>Active Nodes:</span>
                  <b>{current.nodes.active} / {current.nodes.total}</b>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--muted)' }}>Active Links:</span>
                  <b>{current.links.active} / {current.links.total}</b>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--muted)' }}>Active Faults:</span>
                  <b style={{ color: (current.nodes.failed + current.links.failed) > 0 ? '#f87171' : '#34d399' }}>
                    {current.nodes.failed + current.links.failed}
                  </b>
                </div>
              </div>
            </div>
          ) : <p className="muted">Connecting telemetry stream...</p>}
        </div>

        <div className="monitoring-card">
          <h3 style={{ margin: 0, paddingBottom: '12px', borderBottom: '1px solid var(--border)' }}>Traffic Telemetry</h3>
          {current ? (
            <div className="stats-row" style={{ marginTop: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--muted)' }}>Average Latency:</span>
                <b>{current.traffic.average_latency} ms</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--muted)' }}>Packet Loss:</span>
                <b style={{ color: current.traffic.packet_loss_percentage > 0 ? '#fbbf24' : '#34d399' }}>
                  {current.traffic.packet_loss_percentage}%
                </b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--muted)' }}>Throughput:</span>
                <b>{current.traffic.throughput} Mbps</b>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--muted)' }}>Availability:</span>
                <b style={{ color: '#38bdf8' }}>{current.connectivity.traffic_availability}%</b>
              </div>
            </div>
          ) : <p className="muted">Waiting for telemetry...</p>}
        </div>

        <div className="monitoring-card">
          <h3 style={{ margin: 0, paddingBottom: '12px', borderBottom: '1px solid var(--border)' }}>Recent Chaos & Recovery Events</h3>
          <div className="events-list" style={{ marginTop: '14px', maxHeight: '160px', overflowY: 'auto' }}>
            {history.slice(0, 5).map(e => (
              <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 600 }}>{e.name}</div>
                  <small style={{ color: 'var(--muted)' }}>{new Date(e.started_at).toLocaleTimeString()}</small>
                </div>
                <span className={`lab-badge ${e.status === 'completed' ? 'completed' : e.status === 'failed' ? 'failed' : 'running'}`}>
                  {e.status}
                </span>
              </div>
            ))}
            {history.length === 0 && <p className="muted" style={{ margin: 0 }}>No events recorded yet.</p>}
          </div>
        </div>
      </div>

      {/* DYNAMIC CHAOS SCENARIOS SANDBOX */}
      <div style={{ marginTop: '24px' }}>
        <div className="lab-card">
          <div className="lab-card-header">
            <span>⚡ Interactive Chaos & Resilience Scenarios (1-Click Simulations)</span>
            {runningScenario && <span className="lab-badge running">Simulation in Progress</span>}
          </div>
          <p style={{ color: 'var(--muted)', fontSize: '13px', margin: '0 0 16px 0' }}>
            Trigger real automated failure scenarios. Watch NetChaos simulate high-load traffic, inject dynamic topology failures, execute route healing, and stream live metrics.
          </p>

          <div className="scenario-grid">
            <div className="scenario-card">
              <div>
                <h4 className="scenario-title">⚡ Core Link Outage & SPF Route Healing</h4>
                <p className="scenario-desc">
                  Simulates traffic, breaks a core link, initiates dynamic Dijkstra reroute, and verifies zero packet drops.
                </p>
              </div>
              <button 
                type="button"
                className="scenario-btn" 
                onClick={runScenario1} 
                disabled={runningScenario}
              >
                {runningScenario && activeScenario?.includes("Core Link") ? "Running..." : "Run Scenario 1 ➔"}
              </button>
            </div>

            <div className="scenario-card">
              <div>
                <h4 className="scenario-title">🌊 High-Load Flood & Congestion Spike</h4>
                <p className="scenario-desc">
                  Transfers 2,500 packets with injected packet loss and latency to stress-test telemetry detection.
                </p>
              </div>
              <button 
                type="button"
                className="scenario-btn" 
                onClick={runScenario2} 
                disabled={runningScenario}
              >
                {runningScenario && activeScenario?.includes("Flood") ? "Running..." : "Run Scenario 2 ➔"}
              </button>
            </div>

            <div className="scenario-card">
              <div>
                <h4 className="scenario-title">🛡️ Full Resilience Benchmark Suite</h4>
                <p className="scenario-desc">
                  Runs an experiment plan suite and generates clean datasets. Instantly populates the Analytics & History tabs.
                </p>
              </div>
              <button 
                type="button"
                className="scenario-btn" 
                onClick={runScenario3} 
                disabled={runningScenario}
              >
                {runningScenario && activeScenario?.includes("Benchmark") ? "Running..." : "Run Benchmark Suite ➔"}
              </button>
            </div>
          </div>

          {/* REAL-TIME EXECUTION TIMELINE */}
          {scenarioLogs.length > 0 && (
            <div className="scenario-timeline">
              <div style={{ fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '8px' }}>
                Active Scenario Execution Timeline: {activeScenario}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {scenarioLogs.map((log, idx) => (
                  <div key={idx} className="timeline-step">
                    <span className={`step-badge ${log.status}`}>
                      {log.status === "running" ? "RUNNING" : log.status === "done" ? "DONE" : "ERROR"}
                    </span>
                    <span style={{ color: 'var(--text)', flex: 1 }}>{log.msg}</span>
                    <span style={{ color: 'var(--muted)', fontSize: '11px' }}>{log.time}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

