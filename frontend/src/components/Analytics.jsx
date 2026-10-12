import React, { useEffect, useState } from "react";
import { api } from "../api";
import "./Analytics.css";

export function AnalyticsDashboard({ networkId }) {
  const [summary, setSummary] = useState(null);
  const [failures, setFailures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    const fetchAnalytics = async () => {
      setLoading(true);
      setError(null);
      try {
        const sum = await api.getAnalyticsSummary(networkId);
        const fails = await api.getFailureRanking(networkId);
        if (active) {
          setSummary(sum);
          setFailures(fails);
        }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    };
    fetchAnalytics();
    return () => { active = false; };
  }, [networkId]);

  if (loading) return <div className="analytics-loading">Loading Analytics...</div>;
  if (error) return <div className="analytics-error">Error loading analytics: {error}</div>;
  if (!summary) return <div className="analytics-empty">No analytics data available.</div>;

  return (
    <div className="analytics-dashboard">
      <div className="analytics-header">
        <h2>Advanced Resilience Analytics</h2>
        <div className="resilience-score-box">
          <span className="score-label">NetChaos Resilience Score</span>
          <span className="score-value">{summary.resilience_score != null ? summary.resilience_score.toFixed(1) : "N/A"}</span>
        </div>
      </div>

      <div className="analytics-metrics-grid">
        <div className="metric-card">
          <h4>Experiments Analyzed</h4>
          <span className="metric-value">{summary.experiments_analyzed}</span>
        </div>
        <div className="metric-card">
          <h4>Successful Recoveries</h4>
          <span className="metric-value">{summary.successful_recoveries} / {summary.experiments_analyzed}</span>
        </div>
        <div className="metric-card">
          <h4>Average Impact Score</h4>
          <span className="metric-value">
            {summary.average_impact_score != null ? summary.average_impact_score.toFixed(3) : "N/A"}
          </span>
        </div>
        <div className="metric-card">
          <h4>Avg Recovery Time</h4>
          <span className="metric-value">
            {summary.average_recovery_time != null ? `${summary.average_recovery_time.toFixed(2)}s` : "N/A"}
          </span>
        </div>
        <div className="metric-card">
          <h4>Avg Connectivity Preserved</h4>
          <span className="metric-value">
            {summary.average_connectivity_preservation != null 
              ? `${summary.average_connectivity_preservation.toFixed(1)}%` 
              : "N/A"}
          </span>
        </div>
      </div>

      <div className="analytics-section">
        <h3>Failure Impact Ranking</h3>
        {failures.length === 0 ? (
          <p className="no-data">No failure data available to rank.</p>
        ) : (
          <table className="failure-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Experiment</th>
                <th>Failure Type</th>
                <th>Impact Score</th>
                <th>Severity</th>
                <th>Recoverable</th>
                <th>Conn. Preserved</th>
              </tr>
            </thead>
            <tbody>
              {failures.map(f => (
                <tr key={f.experiment_id} className={f.recoverable ? "recoverable-row" : "unrecoverable-row"}>
                  <td>{f.rank}</td>
                  <td>{f.experiment_id}</td>
                  <td>{f.failure_type}</td>
                  <td>{f.impact_score.toFixed(3)}</td>
                  <td>
                    <span className={`severity-badge ${f.severity.toLowerCase()}`}>
                      {f.severity}
                    </span>
                  </td>
                  <td>{f.recoverable ? "Yes" : "No"}</td>
                  <td>{f.connectivity_preservation != null ? `${f.connectivity_preservation.toFixed(1)}%` : "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      <div className="analytics-section">
        <h3>Research Findings</h3>
        <ul className="findings-list">
          {summary.experiments_analyzed > 0 ? (
            <>
              <li>{summary.experiments_analyzed} experiments have been fully analyzed across the network.</li>
              <li>{summary.failed_recoveries} out of {summary.experiments_analyzed} experiments were unable to recover connectivity completely.</li>
              {summary.average_recovery_time != null && (
                <li>When recovery was possible, it took an average of {summary.average_recovery_time.toFixed(2)}s to restore routing.</li>
              )}
              {summary.resilience_score > 80 ? (
                <li>The targeted infrastructure is considered Highly Resilient according to NetChaos models.</li>
              ) : summary.resilience_score > 50 ? (
                <li>The network exhibits Moderate Resilience and is vulnerable to severe combined chaos events.</li>
              ) : (
                <li>The topology has Weak Resilience. It struggles significantly to maintain functionality under adverse conditions.</li>
              )}
            </>
          ) : (
            <li>Not enough experiments have been completed to generate rigorous research findings.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
