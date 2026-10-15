import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

export function DashboardOverview({ networkId, topology, chaosActive, simulations, onRefresh }) {
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [liveStream, setLiveStream] = useState(true);

  const [resetting, setResetting] = useState(false);
  const [toast, setToast] = useState(null);

  const fetchTelemetry = useCallback(async () => {
    if (!networkId) return;
    try {
      const [cur, chaosHist, recHist] = await Promise.all([
        api.getMonitoringCurrent(networkId).catch(() => null),
        api.getChaosHistory(networkId).catch(() => ({ experiments: [] })),
        api.getRecoveryHistory(networkId).catch(() => [])
      ]);
      setCurrent(cur);
      
      const events = [
        ...(chaosHist?.experiments || []).map(c => ({
          id: c.experiment_id,
          name: `Chaos: ${c.name || c.scenario}`,
          started_at: c.started_at || c.created_at,
          status: c.status
        })),
        ...(recHist || []).map(r => ({
          id: r.id || r.recovery_id,
          name: `Recovery: Flow ${r.simulation_id}`,
          started_at: r.created_at || r.recovery_end_time,
          status: (r.recovery_status || r.status || '').toLowerCase()
        }))
      ].sort((a, b) => new Date(b.started_at || 0) - new Date(a.started_at || 0));
      
      setHistory(events);
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

  const handleResetAllChaos = async () => {
    setResetting(true);
    setToast(null);
    try {
      await api.resetChaos(networkId);
      await api.createMonitoringSnapshot(networkId);
      await fetchTelemetry();
      if (onRefresh) await onRefresh();
      setToast("Network healed and previous session data cleared! All chaos, flows, and metrics reset to 100% HEALTHY.");
      setTimeout(() => setToast(null), 4000);
    } catch (e) {
      console.warn("Reset chaos error:", e);
      setToast(`Reset chaos failed: ${e.message}`);
      setTimeout(() => setToast(null), 4000);
    } finally {
      setResetting(false);
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
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
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
            disabled={resetting}
            style={{ padding: '8px 16px', fontSize: '13px', color: '#f87171', fontWeight: 'bold' }}
            title="Heal all severed links and reset all chaos experiments"
          >
            {resetting ? "Healing Network..." : "Heal All & Reset Chaos"}
          </button>
        </div>
      </div>

      {toast && (
        <div style={{
          marginTop: '12px',
          padding: '10px 16px',
          background: 'rgba(16, 185, 129, 0.15)',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          borderRadius: '6px',
          color: '#10b981',
          fontSize: '13px',
          fontWeight: 600,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>{toast}</span>
          <button 
            type="button" 
            onClick={() => setToast(null)} 
            style={{ background: 'none', border: 'none', color: '#10b981', cursor: 'pointer', fontSize: '16px', padding: 0 }}
          >
            ×
          </button>
        </div>
      )}

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
    </div>
  );
}

