import { useState, useEffect } from "react";
import { api } from "../api";
// UI Helpers
const Section = ({ title, children }) => (
  <section className="panel failures">
    <h2>{title}</h2>
    {children}
  </section>
);
const Panel = ({ children }) => (
  <div style={{ backgroundColor: "var(--bg)", padding: "10px", borderRadius: "6px", border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: "8px" }}>
    {children}
  </div>
);
const Title = ({ children }) => <div style={{ fontSize: "12px", fontWeight: "bold", color: "var(--muted)", textTransform: "uppercase", marginBottom: "8px" }}>{children}</div>;
const Row = ({ label, value }) => (
  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", padding: "4px 0", borderBottom: "1px solid var(--border)" }}>
    <span style={{ color: "var(--muted)" }}>{label}</span>
    <span style={{ fontWeight: "500", textAlign: "right" }}>{value}</span>
  </div>
);

export default function Failures({ networkId }) {
  const [baseline, setBaseline] = useState(null);
  const [report, setReport] = useState(null);
  const [affected, setAffected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchState = async () => {
    try {
      setLoading(true);
      setError(null);
      const b = await api.getBaseline(networkId).catch(() => null);
      setBaseline(b);
      const r = await api.getFailureReport(networkId).catch(() => null);
      setReport(r);
      if (r) {
        const a = await api.getAffectedTraffic(networkId).catch(() => ({ affected_simulations: [] }));
        setAffected(a.affected_simulations || []);
      } else {
        setAffected([]);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (networkId) fetchState();
  }, [networkId]);

  const handleCreateBaseline = async () => {
    try {
      setLoading(true);
      await api.createBaseline(networkId);
      await fetchState();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDetectFailures = async () => {
    try {
      setLoading(true);
      await api.detectFailures(networkId);
      await fetchState();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!networkId) return <div className="placeholder">Select or create a network to detect failures</div>;

  return (
    <Section title="FAILURE DETECTION">
      {error && <div className="error-banner">{error}</div>}

      <div style={{ display: "flex", gap: "10px", marginBottom: "15px" }}>
        <button onClick={handleCreateBaseline} disabled={loading} className="danger">
          CREATE BASELINE
        </button>
        <button onClick={handleDetectFailures} disabled={loading} className="danger">
          DETECT FAILURES
        </button>
        <button onClick={fetchState} disabled={loading}>
          REFRESH
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
        <Panel>
          <Title>NETWORK STATUS</Title>
          {report ? (
            <div>
              <Row label="Status" value={
                <span style={{ 
                  color: report.overall_status === 'healthy' ? 'var(--accent)' : 'var(--danger)',
                  fontWeight: 'bold',
                  textTransform: 'uppercase'
                }}>
                  {report.overall_status}
                </span>
              } />
              <Row label="Failed Nodes" value={report.failed_nodes} />
              <Row label="Failed Links" value={report.failed_links} />
              <Row label="Degraded Links" value={report.degraded_links} />
              <Row label="Components" value={report.connected_components} />
              <Row label="Affected Traffic" value={report.affected_simulations} />
              <Row label="Unreachable Pairs" value={report.unreachable_pairs} />
            </div>
          ) : (
            <div className="placeholder">No failure report available</div>
          )}
        </Panel>

        <Panel>
          <Title>DETECTED FAILURES</Title>
          <div className="scroll-list" style={{ maxHeight: "300px" }}>
            {report && report.failures && report.failures.length > 0 ? (
              report.failures.map(f => (
                <div key={f.id} className="history-item" style={{ 
                  borderLeft: `3px solid ${f.severity === 'critical' ? 'var(--danger)' : 'orange'}`,
                  paddingLeft: '10px'
                }}>
                  <div className="title">
                    {f.severity === 'critical' ? '🔴' : '🟡'} {f.failure_type.replace('_', ' ').toUpperCase()} 
                    : {f.target_type} {f.target_id || ''}
                  </div>
                  <div className="muted">{f.description}</div>
                </div>
              ))
            ) : (
              <div className="placeholder">No current failures detected</div>
            )}
          </div>
        </Panel>

        <Panel>
          <Title>AFFECTED TRAFFIC</Title>
          <div className="scroll-list" style={{ maxHeight: "300px" }}>
            {affected && affected.length > 0 ? (
              affected.map(s => (
                <div key={s.simulation_id} className="history-item">
                  <div className="title">{s.simulation_id} ({s.source} → {s.destination})</div>
                  <div className="muted">{s.impact.replace('_', ' ').toUpperCase()}</div>
                  <div className="muted" style={{ fontSize: "0.8rem", color: 'var(--danger)' }}>{s.reason}</div>
                </div>
              ))
            ) : (
              <div className="placeholder">No affected traffic flows</div>
            )}
          </div>
        </Panel>
        
        <Panel>
          <Title>NETWORK PARTITIONS</Title>
          {report && report.connected_components > 1 ? (
             <div className="history-item">
               <div className="title" style={{ color: 'var(--danger)' }}>Network Partition Detected</div>
               <div className="muted">Components: {report.connected_components}</div>
             </div>
          ) : (
             <div className="placeholder">Network is fully connected</div>
          )}
        </Panel>
      </div>
    </Section>
  );
}
