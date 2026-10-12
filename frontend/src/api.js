// Thin wrapper over the REST API. Errors carry the backend's message.
async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error?.message || `Request failed (${response.status})`);
  }
  return data;
}

export const api = {
  listNetworks: () => request("/networks"),
  createNetwork: (name) => request("/networks", { method: "POST", body: { name } }),
  getTopology: (networkId) => request(`/networks/${networkId}/topology`),
  addNode: (networkId, node) => request(`/networks/${networkId}/nodes`, { method: "POST", body: node }),
  deleteNode: (networkId, nodeId) => request(`/networks/${networkId}/nodes/${nodeId}`, { method: "DELETE" }),
  addLink: (networkId, link) => request(`/networks/${networkId}/links`, { method: "POST", body: link }),
  deleteLink: (networkId, linkId) => request(`/networks/${networkId}/links/${linkId}`, { method: "DELETE" }),
  applyTemplate: (networkId, template) =>
    request(`/networks/${networkId}/templates/${template}`, { method: "POST" }),

  // Module 2: traffic simulation
  listSimulations: (networkId) => request(`/networks/${networkId}/traffic/simulations`),
  createSimulation: (networkId, params) =>
    request(`/networks/${networkId}/traffic/simulations`, { method: "POST", body: params }),
  runSimulation: (networkId, simulationId) =>
    request(`/networks/${networkId}/traffic/simulations/${simulationId}/run`, { method: "POST" }),
  getMetrics: (networkId, simulationId) =>
    request(`/networks/${networkId}/traffic/simulations/${simulationId}/metrics`),

  // Module 3: chaos injection. `kind` is the endpoint name: router-failure, link-failure, packet-loss,
  // latency, bandwidth-reduction, congestion or multi-failure.
  injectChaos: (networkId, kind, body) =>
    request(`/networks/${networkId}/chaos/${kind}`, { method: "POST", body }),
  getActiveChaos: (networkId) => request(`/networks/${networkId}/chaos/active`),
  getChaosHistory: (networkId) => request(`/networks/${networkId}/chaos/history`),
  revertChaos: (networkId, experimentId) =>
    request(`/networks/${networkId}/chaos/${experimentId}/revert`, { method: "POST" }),
  resetChaos: (networkId) => request(`/networks/${networkId}/chaos/reset`, { method: "POST" }),

  // Module 4: failure detection
  createBaseline: (networkId) => request(`/networks/${networkId}/failures/baseline`, { method: "POST" }),
  getBaseline: (networkId) => request(`/networks/${networkId}/failures/baseline`),
  detectFailures: (networkId) => request(`/networks/${networkId}/failures/detect`, { method: "POST" }),
  getFailureReport: (networkId) => request(`/networks/${networkId}/failures/report`),
  getFailureHistory: (networkId) => request(`/networks/${networkId}/failures/history`),
  checkConnectivity: (networkId, source, destination) =>
    request(`/networks/${networkId}/failures/connectivity?source=${source}&destination=${destination}`),
  getAffectedTraffic: (networkId) => request(`/networks/${networkId}/failures/affected-traffic`),

  // Module 5: Dynamic Recovery
  recoverSimulation: (networkId, simulationId, strategy = "lowest_latency", opts = {}) =>
    request(`/networks/${networkId}/recovery`, {
      method: "POST",
      body: { simulation_id: simulationId, strategy, ...opts },
    }),
  recoverAll: (networkId, strategy = "lowest_latency") =>
    request(`/networks/${networkId}/recovery/all?strategy=${strategy}`, { method: "POST" }),
  previewRecovery: (networkId, simulationId, strategy = "lowest_latency", opts = {}) =>
    request(`/networks/${networkId}/recovery/preview`, {
      method: "POST",
      body: { simulation_id: simulationId, strategy, ...opts },
    }),
  getMonitoringCurrent: (networkId) => request(`/networks/${networkId}/monitoring/current`),
  createMonitoringSnapshot: (networkId) => request(`/networks/${networkId}/monitoring/snapshot`, { method: "POST" }),
  getMonitoringHistory: (networkId) => request(`/networks/${networkId}/monitoring/history?limit=25`),
  getRecoverySummary: (networkId) => request(`/networks/${networkId}/monitoring/recovery`),
  getRecoveryHistory: (networkId) => request(`/networks/${networkId}/recovery/history`),
  getSimulationRoute: (networkId, simulationId) =>
    request(`/networks/${networkId}/simulations/${simulationId}/route`),
    
  // Module 7: History & Analysis
  getHistory: (networkId) => request(`/networks/${networkId}/history`),
  getExperimentDetail: (experimentId) => request(`/experiments/${experimentId}`),
  createExperiment: (networkId, params) => request(`/networks/${networkId}/experiments`, { method: "POST", body: params }),
  completeExperiment: (experimentId) => request(`/experiments/${experimentId}/complete`, { method: "POST" }),
  getAnalyticsSummary: (networkId) => request(`/networks/${networkId}/analytics/summary`),
  getFailureRanking: (networkId) => request(`/networks/${networkId}/analytics/failures`),

  // runner
  createExperimentPlan: (payload) => request("/experiment-plans", { method: "POST", body: payload }),
  getExperimentPlan: (planId) => request(`/experiment-plans/${planId}`),
  runExperimentPlan: (planId) => request(`/experiment-plans/${planId}/run`, { method: "POST" }),
  cancelExperimentPlan: (planId) => request(`/experiment-plans/${planId}/cancel`, { method: "POST" }),
  getExperimentPlanResults: (planId) => request(`/experiment-plans/${planId}/results`),
};
