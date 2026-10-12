import React, { useState, useEffect } from 'react';

export default function DatasetLab() {
  const [datasets, setDatasets] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [records, setRecords] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [version, setVersion] = useState('1.0');
  const [failureFilter, setFailureFilter] = useState('');

  const fetchDatasets = async () => {
    try {
      const res = await fetch('/api/datasets');
      const data = await res.json();
      setDatasets(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    let filters = {};
    if (failureFilter) {
      filters.failure_types = [failureFilter];
    }
    try {
      const res = await fetch('/api/datasets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description,
          version,
          filters: Object.keys(filters).length ? filters : null
        })
      });
      if (res.ok) {
        await fetchDatasets();
        setName('');
        setDescription('');
        setFailureFilter('');
      } else {
        alert("Generation failed");
      }
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(false);
    }
  };

  const handleSelectDataset = async (dataset_id) => {
    try {
      const res = await fetch(`/api/datasets/${dataset_id}`);
      const data = await res.json();
      setSelectedDataset(data.metadata);
      setRecords(data.records);

      const statsRes = await fetch(`/api/datasets/${dataset_id}/statistics`);
      if (statsRes.ok) {
        setStats(await statsRes.json());
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="lab-container">
      <div className="lab-header">
        <h2 className="lab-title">Research Dataset Lab</h2>
      </div>
      
      <div className="lab-grid-3" style={{ marginBottom: "24px" }}>
        
        {/* Generator Form */}
        <div className="lab-card">
          <div className="lab-card-header">
            <span>Generate Dataset</span>
          </div>
          <form onSubmit={handleGenerate}>
            <div className="lab-form-group">
              <label>Dataset Name</label>
              <input type="text" required value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Resilience Baseline v1" />
            </div>
            <div className="lab-form-group">
              <label>Description</label>
              <input type="text" value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional dataset description" />
            </div>
            <div className="lab-form-group">
              <label>Version</label>
              <input type="text" required value={version} onChange={e=>setVersion(e.target.value)} />
            </div>
            <div className="lab-form-group">
              <label>Filter by Failure Type</label>
              <select value={failureFilter} onChange={e=>setFailureFilter(e.target.value)}>
                <option value="">(All)</option>
                <option value="link_failure">Link Failure</option>
                <option value="router_failure">Router Failure</option>
                <option value="packet_loss">Packet Loss</option>
              </select>
            </div>
            <button type="submit" disabled={generating} style={{ width: "100%", marginTop: "12px" }}>
              {generating ? "Generating..." : "Generate Dataset"}
            </button>
          </form>
        </div>
        
        {/* Dataset List */}
        <div className="lab-card">
          <div className="lab-card-header">
            <span>Available Datasets</span>
            {datasets.length > 0 && <span className="lab-badge valid">{datasets.length} Total</span>}
          </div>
          {loading ? (
             <div className="placeholder" style={{ padding: "40px" }}>Loading datasets...</div>
          ) : datasets.length === 0 ? (
             <div className="placeholder" style={{ padding: "40px" }}>No datasets generated yet. Use the generator on the left to export experiment histories.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="lab-table">
                <thead>
                  <tr>
                    <th>Dataset ID</th>
                    <th>Name</th>
                    <th>Records</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map(ds => (
                    <tr key={ds.dataset_id} style={selectedDataset?.dataset_id === ds.dataset_id ? { background: "rgba(139, 92, 246, 0.15)" } : {}}>
                      <td style={{ fontFamily: "monospace", fontSize: "12px", color: "var(--accent)" }}>{ds.dataset_id}</td>
                      <td style={{ fontWeight: 600 }}>{ds.name} <span style={{ opacity: 0.6, fontSize: "11px" }}>v{ds.version}</span></td>
                      <td>{ds.record_count}</td>
                      <td>
                         <button onClick={() => handleSelectDataset(ds.dataset_id)} style={{ padding: "4px 10px", fontSize: "12px" }}>View</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      
      {/* Detail View */}
      {selectedDataset && (
        <div className="lab-card" style={{ marginTop: "24px" }}>
          <div className="lab-header" style={{ marginBottom: "16px" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "18px", color: "var(--text)" }}>Dataset: {selectedDataset.name} (v{selectedDataset.version})</h3>
              <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--muted)" }}>{selectedDataset.description || "No description provided"}</p>
            </div>
            <div style={{ display: "flex", gap: "10px" }}>
              <a href={`/api/datasets/${selectedDataset.dataset_id}/export/csv`} download style={{ textDecoration: "none" }}>
                <button type="button" style={{ fontSize: "12px", padding: "6px 14px" }}>⬇ Export CSV</button>
              </a>
              <a href={`/api/datasets/${selectedDataset.dataset_id}/export/json`} download style={{ textDecoration: "none" }}>
                <button type="button" style={{ fontSize: "12px", padding: "6px 14px" }}>⬇ Export JSON</button>
              </a>
            </div>
          </div>
          
          {stats && (
            <div className="lab-stats-grid">
              <div className="lab-stat-box">
                <div className="lab-stat-label">Total Records</div>
                <div className="lab-stat-val">{stats.total_records}</div>
              </div>
              <div className="lab-stat-box success">
                <div className="lab-stat-label">Valid Records</div>
                <div className="lab-stat-val">{stats.data_quality_report.VALID || 0}</div>
              </div>
              <div className="lab-stat-box warning">
                <div className="lab-stat-label">Partial Records</div>
                <div className="lab-stat-val">{stats.data_quality_report.PARTIAL || 0}</div>
              </div>
              <div className="lab-stat-box danger">
                <div className="lab-stat-label">Invalid Records</div>
                <div className="lab-stat-val">{stats.data_quality_report.INVALID || 0}</div>
              </div>
            </div>
          )}
          
          <div className="lab-card-header" style={{ marginTop: "20px" }}>
            <span>Preview (first 20 records)</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="lab-table">
              <thead>
                <tr>
                  <th>Quality</th>
                  <th>Experiment ID</th>
                  <th>Chaos</th>
                  <th>Outcome</th>
                  <th>Impact</th>
                  <th>Resilience</th>
                  <th>Rec. Time</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 20).map((r, i) => (
                  <tr key={i}>
                    <td>
                       <span className={`lab-badge ${r.data_quality.toLowerCase()}`}>
                         {r.data_quality}
                       </span>
                    </td>
                    <td style={{ fontFamily: "monospace", fontSize: "11px" }}>{r.experiment_id.slice(0,10)}...</td>
                    <td>{r.chaos_type}</td>
                    <td style={{ fontWeight: 600 }}>{r.recovery_outcome}</td>
                    <td>{r.impact_score != null ? r.impact_score.toFixed(2) : "N/A"}</td>
                    <td>{r.resilience_score != null ? r.resilience_score.toFixed(2) : "N/A"}</td>
                    <td>{r.recovery_time != null ? `${r.recovery_time.toFixed(2)}s` : "N/A"}</td>
                    <td style={{ color: "var(--danger)", fontSize: "11px" }}>{r.validation_warnings?.join(', ') || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
        </div>
      )}
    </div>
  );
}
