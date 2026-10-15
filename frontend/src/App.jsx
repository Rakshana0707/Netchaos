import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import { ActiveChaosPanel, ChaosHistory, ChaosPanel } from "./components/Chaos.jsx";
import { DetailsPanel, LinkForm, NetworkPanel, NodeForm, TemplatePanel } from "./components/Panels.jsx";
import TopologyCanvas from "./components/TopologyCanvas.jsx";
import { TrafficPanel, TrafficResults } from "./components/Traffic.jsx";
import Failures from "./components/Failures.jsx";
import RecoveryPanel from "./components/Recovery.jsx";
import { MonitoringDashboard } from "./components/Monitoring.jsx";
import { DashboardOverview } from "./components/DashboardOverview.jsx";

const EMPTY_TOPOLOGY = { nodes: [], links: [], summary: { nodes: 0, links: 0, active_nodes: 0, active_links: 0 } };

const TABS = ["Dashboard", "Topology", "Traffic", "Chaos", "Failures", "Recovery", "Monitoring"];

export default function App() {
  const [networks, setNetworks] = useState([]);
  const [networkId, setNetworkId] = useState(null);
  const [loadedTopology, setLoadedTopology] = useState(EMPTY_TOPOLOGY);
  const [selection, setSelection] = useState(null);
  const [error, setError] = useState(null);
  const [simulations, setSimulations] = useState([]);
  const [selectedSimId, setSelectedSimId] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [chaosActive, setChaosActive] = useState([]);
  const [chaosHistory, setChaosHistory] = useState([]);
  const [previewRoute, setPreviewRoute] = useState(null);
  
  const [loadingNetworks, setLoadingNetworks] = useState(true);
  const [activeTab, setActiveTab] = useState("Dashboard");
  const [networkStatus, setNetworkStatus] = useState("UNKNOWN");

  const refreshNetworkStatus = useCallback(async (id) => {
    if (!id) {
      setNetworkStatus("UNKNOWN");
      return;
    }
    try {
      const data = await api.getMonitoringCurrent(id);
      if (data?.health_status) {
        setNetworkStatus(data.health_status);
      }
    } catch {
      setNetworkStatus("UNKNOWN");
    }
  }, []);

  const refreshTopology = useCallback(async (id) => {
    if (!id) {
      setLoadedTopology(EMPTY_TOPOLOGY);
      setNetworkStatus("UNKNOWN");
      return;
    }
    const [topo, current] = await Promise.all([
      api.getTopology(id).catch(() => EMPTY_TOPOLOGY),
      api.getMonitoringCurrent(id).catch(() => null)
    ]);
    setLoadedTopology(topo);
    if (current?.health_status) {
      setNetworkStatus(current.health_status);
    }
  }, []);

  const run = useCallback(async (action) => {
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }, []);

  const loadNetworks = useCallback(async (preferredId = null) => {
    setLoadingNetworks(true);
    return run(async () => {
      try {
        const list = await api.listNetworks();
        setNetworks(list || []);
        if (list && list.length > 0) {
          const saved = preferredId || localStorage.getItem("netchaos_active_network");
          const found = list.find(n => n.network_id === saved);
          setNetworkId(found ? found.network_id : list[0].network_id);
        } else {
          setNetworkId(null);
          setActiveTab("Topology");
        }
      } finally {
        setLoadingNetworks(false);
      }
    });
  }, [run]);

  useEffect(() => {
    loadNetworks();
  }, [loadNetworks]);

  useEffect(() => {
    if (networkId) {
      localStorage.setItem("netchaos_active_network", networkId);
    }
  }, [networkId]);

  useEffect(() => {
    setSelection(null);
    run(() => refreshTopology(networkId));
    refreshNetworkStatus(networkId);
  }, [networkId, refreshTopology, refreshNetworkStatus, run]);

  // Live polling for header status sync
  useEffect(() => {
    if (!networkId) return;
    const interval = setInterval(() => {
      refreshNetworkStatus(networkId);
    }, 2500);
    return () => clearInterval(interval);
  }, [networkId, refreshNetworkStatus]);

  // Simulations polling
  useEffect(() => {
    let cancelled = false;
    setSimulations([]);
    setSelectedSimId(null);
    if (!networkId) return;
    run(async () => {
      const list = await api.listSimulations(networkId);
      if (cancelled) return;
      setSimulations(list);
      setSelectedSimId(list[0]?.simulation_id ?? null);
    });
    return () => { cancelled = true; };
  }, [networkId, run]);

  // Chaos details
  const refreshChaos = useCallback(async (id) => {
    const [active, history] = await Promise.all([api.getActiveChaos(id), api.getChaosHistory(id)]);
    setChaosActive(active.active_experiments);
    setChaosHistory(history.experiments);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setChaosActive([]);
    setChaosHistory([]);
    if (!networkId) return;
    run(async () => {
      const [active, history] = await Promise.all([api.getActiveChaos(networkId), api.getChaosHistory(networkId)]);
      if (cancelled) return;
      setChaosActive(active.active_experiments);
      setChaosHistory(history.experiments);
    });
    return () => { cancelled = true; };
  }, [networkId, run]);

  const selectedSim = simulations.find((s) => s.simulation_id === selectedSimId) ?? null;
  const selectedStatus = selectedSim?.status;

  useEffect(() => {
    let cancelled = false;
    setMetrics(null);
    if (networkId && selectedSimId && (selectedStatus === "completed" || selectedStatus === "failed")) {
      api.getMetrics(networkId, selectedSimId).then((m) => !cancelled && setMetrics(m)).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [networkId, selectedSimId, selectedStatus]);

  const createSimulation = (params) =>
    run(async () => {
      const created = await api.createSimulation(networkId, params);
      setSimulations((prev) => [created, ...prev]);
      setSelectedSimId(created.simulation_id);
    });

  const runSimulation = () =>
    run(async () => {
      const done = await api.runSimulation(networkId, selectedSimId);
      setSimulations((prev) => prev.map((s) => (s.simulation_id === done.simulation_id ? done : s)));
    });

  const createNetwork = (name) =>
    run(async () => {
      const created = await api.createNetwork(name);
      const list = await api.listNetworks();
      setNetworks(list);
      setNetworkId(created.network_id);
      setActiveTab("Topology");
    });

  const mutate = (action) =>
    run(async () => {
      await action();
      await refreshTopology(networkId);
    });

  const chaosAction = (action) =>
    run(async () => {
      await action();
      await Promise.all([refreshTopology(networkId), refreshChaos(networkId)]);
      await refreshNetworkStatus(networkId);
    });

  // Derived state
  const hasNetwork = Boolean(networkId);
  const loading = hasNetwork && loadedTopology.network_id !== networkId;
  const topology = loading ? EMPTY_TOPOLOGY : loadedTopology;
  const { summary } = topology;
  
  const showTopologyCanvas = ["Topology", "Traffic", "Chaos", "Failures", "Recovery"].includes(activeTab);

  return (
    <div className="app-layout">
      {/* GLOBAL HEADER */}
      <header className="app-header">
        <div style={{display: 'flex', alignItems: 'center', gap: '16px'}}>
          <b style={{fontSize: '1.25rem', letterSpacing: '-0.02em'}}>NetChaos</b>
          <label style={{display: 'inline-flex', flexDirection: 'row', alignItems: 'center', gap: '8px', margin: 0, flex: 'none'}}>
            <span style={{color: 'var(--muted)', fontSize: '0.9rem'}}>Network:</span>
            <select 
              value={networkId || ""} 
              onChange={e => setNetworkId(e.target.value)}
              disabled={loadingNetworks}
              style={{marginRight: '6px'}}
            >
              {loadingNetworks ? (
                <option value="">Loading networks…</option>
              ) : networks.length === 0 ? (
                <option value="">No networks available</option>
              ) : (
                networks.map(n => <option key={n.network_id} value={n.network_id}>{n.name} ({n.network_id})</option>)
              )}
            </select>
            <button 
              type="button" 
              className="secondary" 
              onClick={() => loadNetworks(networkId)} 
              title="Refresh network list"
              style={{padding: '4px 8px', fontSize: '13px', minHeight: 'unset'}}
            >
              ↻
            </button>
            <button 
              type="button" 
              className="secondary" 
              onClick={() => {
                if (window.confirm("Reset all network simulations, chaos, and data back to original seed dataset?")) {
                  run(async () => {
                    await api.resetDatabase();
                    await loadNetworks();
                  });
                }
              }}
              title="Reset data back to original seed dataset"
              style={{padding: '4px 8px', fontSize: '12px', minHeight: 'unset', marginLeft: '6px'}}
            >
              Reset Data
            </button>
          </label>
        </div>
        <div style={{display:'flex', gap: '20px', alignItems: 'center'}}>
           {hasNetwork && (
             <>
               <span>Nodes: {summary.nodes}</span>
               <span>Links: {summary.links}</span>
               <span className={`status-${networkStatus.toLowerCase()}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                 <span className={`device-beacon ${networkStatus === 'HEALTHY' ? 'active' : networkStatus === 'CRITICAL' ? 'failed' : 'route'}`} style={{ position: 'static' }} />
                 Status: {networkStatus}
               </span>
             </>
           )}
        </div>
      </header>
      
      {/* DASHBOARD BODY */}
      <div className="app-body">
        {/* SIDEBAR NAVIGATION */}
        <aside className="app-sidebar">
          {TABS.map(tab => (
            <button 
              key={tab} 
              className={`nav-tab ${activeTab === tab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
              disabled={!hasNetwork && tab !== 'Topology'}
            >
              {tab}
            </button>
          ))}
        </aside>
        
        {/* MAIN DISPLAY */}
        <main className="app-content">
          {error && (
            <div className="error" role="alert" style={{position:'absolute', zIndex: 1000, width: '100%', top:0}}>
              {error}
              <button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button>
            </div>
          )}
          
          {activeTab === "Dashboard" && hasNetwork && (
             <DashboardOverview 
               networkId={networkId} 
               topology={topology} 
               chaosActive={chaosActive} 
               simulations={simulations} 
               onRefresh={async () => {
                 await Promise.all([
                   refreshTopology(networkId),
                   refreshChaos(networkId),
                   api.listSimulations(networkId).then(list => setSimulations(list || [])).catch(() => setSimulations([]))
                 ]);
                 await refreshNetworkStatus(networkId);
               }}
             />
          )}
          
           {activeTab === "Monitoring" && hasNetwork && (
              <MonitoringDashboard networkId={networkId} nodes={topology.nodes} inline={true} />
           )}
          
          {showTopologyCanvas && (
             <div className="content-panel-wrapper">
               {/* Contextual Side Panel based on Tab */}
               <aside className="side-panel sidebar">
                 {activeTab === "Topology" && (
                   <>
                     <NetworkPanel networks={networks} networkId={networkId} onSelect={setNetworkId} onCreate={createNetwork} />
                     <NodeForm disabled={!hasNetwork} onAdd={(node) => mutate(() => api.addNode(networkId, node))} />
                     <LinkForm nodes={topology.nodes} disabled={!hasNetwork} onAdd={(link) => mutate(() => api.addLink(networkId, link))} />
                     <TemplatePanel disabled={!hasNetwork || loading} isEmpty={summary.nodes === 0} onApply={(template) => mutate(() => api.applyTemplate(networkId, template))} />
                     <DetailsPanel selection={selection} topology={topology} onDeleteNode={(node) => mutate(() => api.deleteNode(networkId, node.id)).then(() => setSelection(null))} onDeleteLink={(link) => mutate(() => api.deleteLink(networkId, link.id)).then(() => setSelection(null))} />
                   </>
                 )}
                 
                 {activeTab === "Traffic" && (
                   <>
                     <TrafficPanel nodes={topology.nodes} disabled={!hasNetwork || loading} selectedSim={selectedSim} onCreate={createSimulation} onRun={runSimulation} />
                   </>
                 )}
                 
                 {activeTab === "Chaos" && (
                   <>
                     <ChaosPanel nodes={topology.nodes} links={topology.links} disabled={!hasNetwork || loading} onInject={(kind, body) => chaosAction(() => api.injectChaos(networkId, kind, body))} />
                     <ActiveChaosPanel active={chaosActive} disabled={!hasNetwork || loading} onRevert={(id) => chaosAction(() => api.revertChaos(networkId, id))} onReset={() => chaosAction(() => api.resetChaos(networkId))} />
                     <ChaosHistory history={chaosHistory} />
                   </>
                 )}
                 
                 {activeTab === "Failures" && (
                    <Failures networkId={networkId} />
                 )}
                 
                 {activeTab === "Recovery" && (
                    <RecoveryPanel 
                      networkId={networkId} 
                      simulations={simulations} 
                      selectedSimId={selectedSimId} 
                      onSelectSim={(simId) => {
                        setSelectedSimId(simId);
                        setPreviewRoute(null);
                      }}
                      onPreviewRoute={setPreviewRoute} 
                      nameOf={(id) => topology.nodes.find((n) => n.id === id)?.name ?? id}
                      onRecovered={(recoveryData) => {
                        if (recoveryData?.recovered_route) {
                          setPreviewRoute(recoveryData.recovered_route);
                        }
                        api.createMonitoringSnapshot(networkId).catch(() => null);
                        api.listSimulations(networkId).then(list => setSimulations(list));
                        run(() => refreshTopology(networkId));
                        api.getMonitoringCurrent(networkId).then(data => setNetworkStatus(data.health_status));
                      }}
                    />
                 )}
               </aside>
               
               {/* Topology Canvas rendered next to the Contextual panels */}
                {/* Canvas & Bottom Dock */}
                <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0, height: "100%", overflow: "hidden" }}>
                  <div className="canvas" style={{ flex: 1, minHeight: 0, position: "relative" }}>
                 {hasNetwork ? (
                   <TopologyCanvas
                     topology={topology} selection={selection} onSelect={setSelection} resetKey={`${networkId}-${activeTab}`}
                     route={previewRoute || (selectedSim?.route ?? null)} chaos={chaosActive}
                   />
                 ) : (
                   <p className="empty">Create a network to get started.</p>
                 )}
                 {hasNetwork && !loading && summary.nodes === 0 && <p className="empty">Add nodes or generate a template.</p>}
                  </div>
                  {activeTab === "Traffic" && hasNetwork && (
                    <TrafficResults
                      simulations={simulations}
                      selectedId={selectedSimId}
                      metrics={metrics}
                      nameOf={(id) => topology.nodes.find((n) => n.id === id)?.name ?? id}
                      onSelect={setSelectedSimId}
                    />
                  )}
                </div>
             </div>
          )}
        </main>
      </div>
    </div>
  );
}
