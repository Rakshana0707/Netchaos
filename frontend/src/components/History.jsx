import React, { useState, useEffect } from 'react';
import { api } from '../api';

const fmt = (v, unit = "") => (v == null ? "N/A (undefined)" : `${+Number(v).toFixed(2)}${unit}`);

export function HistoryDashboard({ networkId, onClose, inline = false }) {
  const [experiments, setExperiments] = useState([]);

  const [selectedExp, setSelectedExp] = useState(null);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (networkId) {
      api.getHistory(networkId).then(setExperiments).catch(e => console.error(e));
    }
  }, [networkId]);

  useEffect(() => {
    if (selectedExp) {
      api.getExperimentDetail(selectedExp).then(setDetail).catch(e => console.error(e));
    }
  }, [selectedExp]);

  const createExperiment = async () => {
    const name = prompt("Experiment Name:", "Module 7 Test");
    if (!name) return;
    const desc = prompt("Description:", "Evaluating automatic history");
    await api.createExperiment(networkId, { name, description: desc });
    api.getHistory(networkId).then(setExperiments);
  };
  
  const completeExperiment = async (id) => {
    await api.completeExperiment(id);
    api.getHistory(networkId).then(setExperiments);
  };

  return (
    <div className={`monitoring-overlay ${inline ? 'inline' : ''}`}>
      <div className="monitoring-header">
        <h2>History & Analysis</h2>
        <div className="monitoring-actions">
          <button className="button" onClick={createExperiment}>+ New Experiment</button>
          {!inline && onClose && <button className="button" onClick={onClose} style={{ marginLeft: '10px' }}>Close</button>}
        </div>
      </div>

      
      {!selectedExp ? (
        <div className="monitoring-card">
          <h3>Experiment History</h3>
          <table className="details-table" style={{width: '100%'}}>
            <thead>
              <tr><th>Name</th><th>Status</th><th>Started</th><th>Ended</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {experiments.map(e => (
                <tr key={e.id}>
                  <td>{e.name}</td>
                  <td>{e.status}</td>
                  <td>{new Date(e.started_at).toLocaleString()}</td>
                  <td>{e.ended_at ? new Date(e.ended_at).toLocaleString() : '-'}</td>
                  <td>
                    <button onClick={() => setSelectedExp(e.id)}>View Details</button>
                    {e.status === 'CREATED' && <button onClick={() => completeExperiment(e.id)}>Complete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {experiments.length === 0 && <p>No experiments found.</p>}
        </div>
      ) : (
        <div className="history-detail-view">
          <button onClick={() => setSelectedExp(null)}>← Back to List</button>
          {detail ? (
            <div style={{ marginTop: '20px' }}>
              <h3>Experiment: {detail.experiment.name} (<span className={`status-${detail.experiment.status.toLowerCase()}`}>{detail.experiment.status}</span>)</h3>
              <p>{detail.experiment.description}</p>
              
              <div className="monitoring-dashboard-grid" style={{marginTop: '20px'}}>
                <div className="monitoring-card">
                  <h4>Performance Analysis (Baseline vs Worst)</h4>
                  {detail.performance_analysis ? (
                    <table className="details-table">
                      <tbody>
                        <tr><td>Latency Degradation:</td><td>{fmt(detail.performance_analysis.latency.degradation_absolute, " ms")}</td></tr>
                        <tr><td>Packet Loss:</td><td>{fmt(detail.performance_analysis.packet_loss.worst, "%")}</td></tr>
                        <tr><td>Throughput:</td><td>{fmt(detail.performance_analysis.throughput.worst, " Mbps")}</td></tr>
                        <tr><td>Availability:</td><td>{fmt(detail.performance_analysis.availability.worst, "%")}</td></tr>
                      </tbody>
                    </table>
                  ) : <p>No performance data.</p>}
                  {detail.metrics && (
                    <table className="details-table" style={{marginTop: 12}}>
                      <tbody>
                        <tr><td>Recovery status:</td><td>{detail.metrics.recovery_status}</td></tr>
                        <tr><td>Connectivity kept:</td><td>{fmt(detail.metrics.connectivity_preservation, "%")}</td></tr>
                        <tr><td>Recovery time (simulated):</td><td>{fmt(detail.metrics.recovery_time_seconds, " s")}</td></tr>
                        <tr><td>Impact score:</td><td>{fmt(detail.metrics.impact_score)}</td></tr>
                        {detail.metrics.missing?.length > 0 && <tr><td>Missing data:</td><td>{detail.metrics.missing.join("; ")}</td></tr>}
                      </tbody>
                    </table>
                  )}
                </div>
                
                <div className="monitoring-card">
                  <h4>Failure Impact Assessment</h4>
                  {detail.failure_impacts && detail.failure_impacts.length > 0 ? detail.failure_impacts.map((f, i) => (
                    <div key={i} style={{marginBottom:'10px'}}>
                      <div><b>{f.failure_type}</b> (Impact: {f.impact_score == null ? "N/A" : f.impact_score})</div>
                      <div>Traffic affected: {f.affected_traffic} flow(s)</div>
                      <div>Partitions: {f.partitions_created}</div>
                    </div>
                  )) : <p>No failures observed.</p>}
                </div>
                
                <div className="monitoring-card">
                  <h4>Recovery Effectiveness</h4>
                  {detail.performance_analysis && detail.performance_analysis.packet_loss.recovery_effectiveness !== undefined ? (
                    <div>Overall Effectiveness Score: <b>{detail.performance_analysis.packet_loss.recovery_effectiveness}%</b></div>
                  ) : <p>No recovery data.</p>}
                </div>
              </div>

              <div className="monitoring-card" style={{marginTop: '20px'}}>
                <h4>Event Timeline</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {detail.timeline.map((t, i) => (
                    <div key={i} style={{ padding: '10px', background: 'var(--bg-root)', borderLeft: '4px solid var(--primary)' }}>
                      <span style={{color: '#888', marginRight: '15px'}}>{new Date(t.timestamp).toLocaleTimeString()}</span>
                      <b>{t.event_type}</b>: {t.description}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : <p>Loading details...</p>}
        </div>
      )}
    </div>
  );
}
