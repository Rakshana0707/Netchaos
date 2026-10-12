import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { api } from '../api';

export function MonitoringDashboard({ networkId, onClose, inline = false }) {
  const [current, setCurrent] = useState(null);

  const [history, setHistory] = useState([]);
  const [recovery, setRecovery] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  
  const refresh = async () => {
    if (!networkId) return;
    try {
      const cur = await api.getMonitoringCurrent(networkId);
      const hist = await api.getMonitoringHistory(networkId);
      const rec = await api.getRecoverySummary(networkId);
      setCurrent(cur);
      // Reverse historical data for left-to-right timeline representation
      setHistory([...hist].reverse());
      setRecovery(rec);
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
      interval = setInterval(refresh, 3000);
    }
    return () => clearInterval(interval);
  }, [networkId, autoRefresh]);

  if (!current) return <div className={`monitoring-overlay ${inline ? 'inline' : ''}`}><div className="monitoring-card">Loading Monitoring Metrics...</div></div>;

  const chartData = history.map(h => ({

    time: new Date(h.timestamp).toLocaleTimeString(),
    latency: h.traffic.average_latency,
    packetLoss: h.traffic.packet_loss_percentage,
    throughput: h.traffic.throughput,
    availability: h.connectivity.traffic_availability
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
              <div>Avg Time: <b>{recovery.average_recovery_time} s</b></div>
              <div>Conn Restored: <b>{recovery.connectivity_restored_percentage}%</b></div>
            </div>
          )}
        </div>
      </div>
      
      <div className="monitoring-charts">
        <div className="chart-box">
          <h4>Latency over Time (ms)</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="latency" stroke="#8884d8" name="Latency (ms)" isAnimationActive={false} />
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
              <Line type="monotone" dataKey="packetLoss" stroke="#82ca9d" name="Packet Loss (%)" isAnimationActive={false} />
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
              <Line type="monotone" dataKey="throughput" stroke="#ffc658" name="Throughput (Mbps)" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
