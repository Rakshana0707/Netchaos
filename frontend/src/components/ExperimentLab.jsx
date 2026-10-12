import React, { useState, useEffect } from "react";
import { api } from "../api";

export function ExperimentLab({ networkId }) {
  const [plans, setPlans] = useState([]);
  const [activeTab, setActiveTab] = useState("builder");
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [results, setResults] = useState(null);
  
  // Form State
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [repetitions, setRepetitions] = useState(1);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [packetCount, setPacketCount] = useState(100);
  const [packetSize, setPacketSize] = useState(1024);
  const [chaosType, setChaosType] = useState("link_failure");
  const [chaosTarget, setChaosTarget] = useState("");
  const [isSweep, setIsSweep] = useState(false);
  const [sweepParam, setSweepParam] = useState("loss_percentage");
  const [sweepValuesStr, setSweepValuesStr] = useState("1,5,10,20");
  const [recoveryEnabled, setRecoveryEnabled] = useState(true);
  
  // Data State
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pollingId, setPollingId] = useState(null);

  useEffect(() => {
    if (networkId) {
      api.getTopology(networkId).then((data) => {
        setNodes(data.nodes || []);
        setLinks(data.links || []);
      });
      loadPlans();
    }
  }, [networkId]);

  useEffect(() => {
    if (selectedPlan && selectedPlan.status === "RUNNING") {
      const p = setInterval(() => reloadPlanStatus(selectedPlan.plan_id), 2000);
      setPollingId(p);
      return () => clearInterval(p);
    }
  }, [selectedPlan]);

  const loadPlans = async () => {
    try {
        // Mock get/list endpoint if it isn't listed in runner, or use custom polling logic
        // We'll trust create and single fetching for now.
    } catch (e) {
        console.error(e);
    }
  };

  const reloadPlanStatus = async (planId) => {
    try {
       const res = await api.getExperimentPlan(planId);
       setSelectedPlan(res);
       
       if (["COMPLETED", "FAILED", "PARTIAL", "CANCELLED"].includes(res.status)) {
           fetchResults(planId);
       }
    } catch(e) {
       console.error("Failed to poll plan status:", e);
    }
  };
  
  const fetchResults = async (planId) => {
      try {
          const res = await api.getExperimentPlanResults(planId);
          setResults(res);
      } catch (err) {
          console.error("Failed to fetch plan results:", err);
      }
  };

  const startExperiment = async () => {
    setError(null);
    setLoading(true);
    let sweepObj = null;
    let expectedRuns = repetitions;
    
    if (isSweep) {
        let vals = sweepValuesStr.split(",").map(v => parseFloat(v.trim()));
        sweepObj = {
            parameter: sweepParam,
            values: vals
        };
        expectedRuns *= vals.length;
    }
    
    if (expectedRuns > 100) {
        setError("Cannot exceed 100 maximum runs per batch.");
        setLoading(false);
        return;
    }
    
    try {
        const payload = {
            name: name || "Automated Experiment",
            description,
            network_id: networkId,
            traffic: {
                source,
                destination: target,
                packet_count: parseInt(packetCount),
                packet_size: parseInt(packetSize),
                protocol: "TCP"
            },
            chaos: {
                type: chaosType,
                target: chaosTarget,
                parameters: {
                    loss_percentage: chaosType === 'packet_loss' ? 10 : undefined,
                    additional_latency_ms: chaosType === 'latency' ? 50 : undefined,
                    reduction_percentage: chaosType === 'bandwidth_reduction' ? 50 : undefined,
                }
            },
            recovery: {
                enabled: recoveryEnabled,
                strategy: "shortest_hop"
            },
            repetitions: parseInt(repetitions),
            sweep: sweepObj
        };
        
        const plan = await api.createExperimentPlan(payload);
        
        // Start run natively!
        await api.runExperimentPlan(plan.plan_id);
        
        setSelectedPlan(plan);
        setActiveTab("active");
        
        // Wait 1s and refresh
        setTimeout(() => reloadPlanStatus(plan.plan_id), 1000);
        
    } catch (err) {
        setError(err.message || "Failed to create experiment from configuration");
    } finally {
        setLoading(false);
    }
  };

  const cancelExperiment = async () => {
      if (!selectedPlan) return;
      try {
          await api.cancelExperimentPlan(selectedPlan.plan_id);
          reloadPlanStatus(selectedPlan.plan_id);
      } catch(e) {
          setError(e.message);
      }
  };

  if (!networkId) return <div className="placeholder" style={{ padding: "40px" }}>Pick a network to use the Experiment Lab.</div>;

  return (
    <div className="lab-container">
      <div className="lab-header">
        <h2 className="lab-title">Automated Experiment Lab</h2>
        <div className="lab-tabs">
          <button 
            className={`lab-tab-btn ${activeTab === 'builder' ? 'active' : ''}`}
            onClick={() => setActiveTab('builder')}
          >
            Builder
          </button>
          <button 
            className={`lab-tab-btn ${activeTab === 'active' ? 'active' : ''}`}
            onClick={() => setActiveTab('active')}
            disabled={!selectedPlan}
          >
            Active Run
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: "20px" }}>
          {error}
        </div>
      )}

      {activeTab === "builder" && (
        <div className="lab-grid-2">
          <div className="lab-card">
            <div className="lab-card-header">
              <span>Batch Run Configuration</span>
            </div>
            
            <div className="lab-form-group">
              <label>Experiment Plan Name</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Failure Sensitivity Analysis" />
            </div>
            
            <div className="lab-section-box">
              <h4>Traffic Baseline</h4>
              <div className="lab-form-row">
                <div>
                  <label>Source Node</label>
                  <select value={source} onChange={e => setSource(e.target.value)}>
                    <option value="">Select source...</option>
                    {nodes.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                  </select>
                </div>
                <div>
                  <label>Destination Node</label>
                  <select value={target} onChange={e => setTarget(e.target.value)}>
                    <option value="">Select destination...</option>
                    {nodes.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <div className="lab-section-box danger">
              <h4>Chaos Settings</h4>
              <div className="lab-form-row">
                <div>
                  <label>Failure Type</label>
                  <select value={chaosType} onChange={e => setChaosType(e.target.value)}>
                    <option value="link_failure">Link Failure</option>
                    <option value="router_failure">Router Failure</option>
                    <option value="packet_loss">Packet Loss</option>
                    <option value="latency">Latency Increase</option>
                  </select>
                </div>
                <div>
                  <label>Target Element</label>
                  <select value={chaosTarget} onChange={e => setChaosTarget(e.target.value)}>
                    <option value="">Select target...</option>
                    {chaosType.includes("link") || chaosType.includes("packet") || chaosType.includes("latency") ? 
                      links.map(l => <option key={l.id} value={l.id}>Link {l.source_node_id} ➔ {l.destination_node_id}</option>) :
                      nodes.map(n => <option key={n.id} value={n.id}>Node {n.name}</option>)
                    }
                  </select>
                </div>
              </div>
            </div>

            <div className="lab-section-box purple">
              <h4>Testing Strategy</h4>
              <div className="lab-form-row">
                <div>
                  <label>Repetitions Per Run</label>
                  <input type="number" min="1" max="10" value={repetitions} onChange={e => setRepetitions(e.target.value)} />
                </div>
                <div style={{ display: "flex", alignItems: "center", paddingTop: "20px" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", color: "var(--text)" }}>
                    <input type="checkbox" checked={recoveryEnabled} onChange={e => setRecoveryEnabled(e.target.checked)} />
                    <span>Dynamic Recovery</span>
                  </label>
                </div>
              </div>
            </div>
            
            <div className="lab-section-box warning">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <h4>Parameter Sweep</h4>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "12px", color: "var(--muted)" }}>
                  <input type="checkbox" checked={isSweep} onChange={e => setIsSweep(e.target.checked)} />
                  <span>Enable Sweep</span>
                </label>
              </div>
              {isSweep && (
                <div className="lab-form-row">
                  <div>
                    <label>Parameter</label>
                    <select value={sweepParam} onChange={e => setSweepParam(e.target.value)}>
                      <option value="packet_count">Traffic: Packet Count</option>
                      <option value="packet_size">Traffic: Packet Size</option>
                      <option value="loss_percentage">Chaos: Packet Loss (%)</option>
                      <option value="additional_latency_ms">Chaos: Latency (ms)</option>
                    </select>
                  </div>
                  <div>
                    <label>Sweep Values (CSV)</label>
                    <input type="text" value={sweepValuesStr} onChange={e => setSweepValuesStr(e.target.value)} placeholder="e.g. 10,20,50,100" />
                  </div>
                </div>
              )}
            </div>

            <button 
              onClick={startExperiment} 
              disabled={loading || !source || !target || !chaosTarget}
              style={{ width: "100%", padding: "12px", fontSize: "15px", fontWeight: "700", marginTop: "10px" }}
            >
              {loading ? "Initializing..." : `Launch ${isSweep ? sweepValuesStr.split(",").length * repetitions : repetitions} Simulations 🚀`}
            </button>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div className="lab-card" style={{ background: "linear-gradient(135deg, rgba(30, 27, 75, 0.7), rgba(15, 23, 42, 0.7))" }}>
              <div className="lab-card-header" style={{ color: "#a5b4fc" }}>
                <span>What is Experiment Lab? 🔬</span>
              </div>
              <p style={{ color: "var(--muted)", fontSize: "13px", lineHeight: "1.6", margin: "0 0 16px 0" }}>
                Experiment Lab automatically schedules, runs, and evaluates batch chaos simulations across your active topology.
              </p>
              <ul style={{ margin: 0, paddingLeft: "18px", color: "#cbd5e1", fontSize: "13px", lineHeight: "1.8" }}>
                <li>Validates network state consistently across repeated cycles</li>
                <li>Simulates traffic routes, injects chaos events, and captures failure metrics</li>
                <li>Evaluates dynamic route healing and recalculates reachability</li>
                <li>Exports rigorous CSV and JSON datasets for research and benchmarking</li>
              </ul>
            </div>

            <div className="lab-card">
              <div className="lab-card-header">
                <span>Pre-Flight Checklist</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div className={`lab-badge ${source && target ? 'valid' : 'invalid'}`} style={{ padding: "8px 12px", borderRadius: "6px" }}>
                  {source && target ? '✓ Traffic Flow Configured' : '○ Missing Source or Target Node'}
                </div>
                <div className={`lab-badge ${chaosTarget ? 'valid' : 'invalid'}`} style={{ padding: "8px 12px", borderRadius: "6px" }}>
                  {chaosTarget ? '✓ Chaos Target Selected' : '○ Missing Chaos Target Element'}
                </div>
                <div className={`lab-badge ${(!isSweep || (sweepValuesStr.length && sweepValuesStr.split(',').length > 0)) ? 'valid' : 'partial'}`} style={{ padding: "8px 12px", borderRadius: "6px" }}>
                  {!isSweep ? '✓ Single Run Strategy' : (sweepValuesStr.length ? '✓ Parameter Sweep Bounds Configured' : '○ Enter Sweep Values')}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "active" && selectedPlan && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div className="lab-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "20px" }}>{selectedPlan.name}</h3>
                <span style={{ fontSize: "12px", color: "var(--muted)", fontFamily: "monospace" }}>Plan ID: {selectedPlan.plan_id}</span>
              </div>
              <span className={`lab-badge ${selectedPlan.status.toLowerCase()}`} style={{ fontSize: "12px", padding: "4px 12px" }}>
                {selectedPlan.status}
              </span>
            </div>
            
            <div style={{ marginBottom: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px", color: "var(--muted)", marginBottom: "6px" }}>
                <span>Progress ({selectedPlan.completed_runs} / {selectedPlan.total_runs} runs)</span>
                <span>{Math.round(selectedPlan.progress_percentage || 0)}%</span>
              </div>
              <div className="lab-progress-bar">
                <div className="lab-progress-fill" style={{ width: `${Math.max(2, selectedPlan.progress_percentage || 0)}%` }}></div>
              </div>
            </div>

            {selectedPlan.status === 'RUNNING' && (
              <button onClick={cancelExperiment} className="danger" style={{ padding: "8px 16px" }}>
                Cancel Execution
              </button>
            )}
          </div>

          {results && (
            <div className="lab-card">
              <div className="lab-header" style={{ marginBottom: "16px" }}>
                <h3 style={{ margin: 0, fontSize: "18px" }}>Batch Results</h3>
                <div style={{ display: "flex", gap: "8px" }}>
                  <a href={`/api/experiment-plans/${selectedPlan.plan_id}/export/csv`} download style={{ textDecoration: "none" }}>
                    <button type="button" style={{ fontSize: "12px", padding: "6px 12px" }}>⬇ Export CSV</button>
                  </a>
                  <a href={`/api/experiment-plans/${selectedPlan.plan_id}/export/json`} download style={{ textDecoration: "none" }}>
                    <button type="button" style={{ fontSize: "12px", padding: "6px 12px" }}>⬇ Export JSON</button>
                  </a>
                </div>
              </div>
              
              <div style={{ overflowX: "auto" }}>
                <table className="lab-table">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Scenario</th>
                      <th>Impact Score (0–1)</th>
                      <th>Recovery Success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.results.map((r, i) => (
                      <tr key={r.run_id}>
                        <td style={{ fontWeight: 600 }}>Run {i + 1}</td>
                        <td style={{ color: "var(--muted)" }}>
                          {r.scenario.sweep_parameter ? `${r.scenario.sweep_parameter}: ${r.scenario.sweep_value}` : `Rep ${r.scenario.repetition}`}
                        </td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <div style={{ width: "60px", height: "6px", background: "rgba(255,255,255,0.1)", borderRadius: "3px", overflow: "hidden" }}>
                              <div style={{ height: "100%", width: `${(r.analytics.impact_score ?? 0) * 100}%`, background: "var(--accent)" }}></div>
                            </div>
                            <span style={{ fontSize: "12px" }}>{r.analytics.impact_score == null ? "N/A" : r.analytics.impact_score.toFixed(2)}</span>
                          </div>
                        </td>
                        <td>
                          <span className={`lab-badge ${
                            r.analytics.recovery_status === "recovered" ? "valid" :
                            r.analytics.recovery_status === "not_required" ? "valid" :
                            r.analytics.recovery_status === "unrecoverable" ? "invalid" : "partial"
                          }`}>
                            {r.analytics.recovery_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          
          <div className="lab-card">
            <div className="lab-card-header">
              <span>Run Log</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {selectedPlan.runs.map((r) => (
                <div key={r.run_id} className="history-item" style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span className={`lab-badge ${r.status.toLowerCase()}`}>{r.status}</span>
                    <span style={{ fontWeight: 600, fontSize: "13px" }}>Run {r.run_number}</span>
                    <span style={{ color: "var(--muted)", fontSize: "12px" }}>
                      {r.configuration.sweep_parameter && `${r.configuration.sweep_parameter}=${r.configuration.sweep_value} | `} 
                      Repetition {r.configuration.repetition}
                    </span>
                  </div>
                  {r.error && <span style={{ color: "var(--danger)", fontSize: "12px" }}>{r.error}</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
