import { useState } from "react";

// What each scenario needs. `kind` is the REST endpoint; `fields` are the numeric inputs shown for it.
export const SCENARIOS = {
  router_failure: { label: "Router Failure", action: "Inject Failure", kind: "router-failure", target: "node", fields: [] },
  link_failure: { label: "Link Failure", action: "Fail Link", kind: "link-failure", target: "link", fields: [] },
  packet_loss: {
    label: "Packet Loss", action: "Inject Packet Loss", kind: "packet-loss", target: "link",
    fields: [{ key: "packet_loss", label: "Packet Loss", unit: "%", min: 0, max: 100, start: "30" }],
  },
  latency: {
    label: "Latency", action: "Inject Latency", kind: "latency", target: "link",
    fields: [{ key: "latency", label: "Latency", unit: "ms", min: 0, start: "150" }],
  },
  bandwidth_reduction: {
    label: "Bandwidth Reduction", action: "Reduce Bandwidth", kind: "bandwidth-reduction", target: "link",
    fields: [{ key: "bandwidth", label: "Bandwidth", unit: "Mbps", min: 0, minExclusive: true, start: "20" }],
  },
  congestion: {
    label: "Network Congestion", action: "Inject Congestion", kind: "congestion", target: "link",
    fields: [
      { key: "latency_increase", label: "Latency Increase", unit: "ms", min: 0, start: "50" },
      { key: "bandwidth_reduction_percent", label: "Bandwidth Reduction", unit: "%", min: 0, max: 100, maxExclusive: true, start: "40" },
      { key: "packet_loss", label: "Packet Loss", unit: "%", min: 0, max: 100, start: "10" },
    ],
  },
  multi_failure: { label: "Multiple Failures", action: "Inject Multi-Failure", kind: "multi-failure" },
};
const SINGLE = Object.keys(SCENARIOS).filter((s) => s !== "multi_failure");

const startValues = () =>
  Object.fromEntries(SINGLE.flatMap((s) => SCENARIOS[s].fields.map((f) => [`${s}.${f.key}`, f.start])));

// null when fine, otherwise a short message.
function problem(field, raw) {
  if (raw === "" || Number.isNaN(Number(raw))) return `${field.label} must be a number`;
  const n = Number(raw);
  if (field.min != null && (field.minExclusive ? n <= field.min : n < field.min)) {
    return `${field.label} must be ${field.minExclusive ? "greater than" : "at least"} ${field.min}`;
  }
  if (field.max != null && (field.maxExclusive ? n >= field.max : n > field.max)) {
    return `${field.label} must be ${field.maxExclusive ? "below" : "at most"} ${field.max}`;
  }
  return null;
}

const linkName = (link, nameOf) => `${nameOf(link.source)} ↔ ${nameOf(link.destination)}`;

// API body for one scenario/target/values combination (without the multi-failure "type").
function paramsOf(scenario, target, values) {
  const spec = SCENARIOS[scenario];
  const body = spec.target === "node" ? { node_id: target } : { link_id: target };
  for (const f of spec.fields) body[f.key] = Number(values[`${scenario}.${f.key}`]);
  return body;
}

function Scenario({ scenario, nodes, links, target, onTarget, values, onValue, disabled }) {
  const spec = SCENARIOS[scenario];
  const nameOf = (id) => nodes.find((n) => n.id === id)?.name ?? id;
  const failing = scenario === "router_failure" || scenario === "link_failure";
  const options =
    spec.target === "node"
      ? nodes.filter((n) => n.type === "router").map((n) => ({ id: n.id, text: n.name, status: n.status }))
      : links.map((l) => ({ id: l.id, text: linkName(l, nameOf), status: l.status }));
  return (
    <>
      <label>
        {spec.target === "node" ? "Target Router" : "Target Link"}
        <select value={target} onChange={(e) => onTarget(e.target.value)} disabled={disabled}>
          <option value="">{spec.target === "node" ? "Select router…" : "Select link…"}</option>
          {options.map((o) => (
            <option key={o.id} value={o.id} disabled={failing && o.status !== "active"}>
              {o.text}{o.status !== "active" ? " (failed)" : ""}
            </option>
          ))}
        </select>
      </label>
      {spec.fields.map((f) => (
        <label key={f.key}>
          {f.label} ({f.unit})
          <input
            type="number" step="any" value={values[`${scenario}.${f.key}`]} disabled={disabled}
            onChange={(e) => onValue(`${scenario}.${f.key}`, e.target.value)}
          />
        </label>
      ))}
    </>
  );
}

function isValid(scenario, target, values) {
  const spec = SCENARIOS[scenario];
  return Boolean(target) && spec.fields.every((f) => problem(f, values[`${scenario}.${f.key}`]) === null);
}

function firstProblem(scenario, values) {
  const spec = SCENARIOS[scenario];
  return spec.fields.map((f) => problem(f, values[`${scenario}.${f.key}`])).find(Boolean) ?? null;
}

// "Link Failure: Router-A ↔ Router-B" or "Packet Loss: Router-A ↔ Router-B (30%)" for the batch list.
function describeQueued(event, nameOf, linkOf) {
  const where = event.type === "router_failure" ? nameOf(event.node_id) : linkOf(event.link_id);
  const numbers = SCENARIOS[event.type].fields.map((f) => `${event[f.key]}${f.unit}`).join(", ");
  return `${SCENARIOS[event.type].label}: ${where}${numbers ? ` (${numbers})` : ""}`;
}

export function ChaosPanel({ nodes, links, disabled, onInject }) {
  const [scenario, setScenario] = useState("router_failure");
  const [batchScenario, setBatchScenario] = useState("link_failure");
  const [targets, setTargets] = useState({});
  const [values, setValues] = useState(startValues);
  const [batch, setBatch] = useState([]);
  const isMulti = scenario === "multi_failure";
  const active = isMulti ? batchScenario : scenario;
  const target = targets[active] ?? "";
  const nameOf = (id) => nodes.find((n) => n.id === id)?.name ?? id;
  const linkOf = (id) => {
    const l = links.find((x) => x.id === id);
    return l ? linkName(l, nameOf) : id;
  };

  const valid = isValid(active, target, values);
  const hint = firstProblem(active, values);
  const eventBody = () => paramsOf(active, target, values);

  const submit = async (event) => {
    event.preventDefault();
    if (isMulti) {
      if (batch.length === 0) return;
      const done = await onInject("multi-failure", { events: batch });
      if (done) setBatch([]);
    } else {
      await onInject(SCENARIOS[scenario].kind, eventBody());
    }
  };

  return (
    <section className="panel chaos">
      <h2>Chaos Control</h2>
      <form onSubmit={submit}>
        <label>
          Scenario
          <select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={disabled}>
            {Object.entries(SCENARIOS).map(([key, s]) => <option key={key} value={key}>{s.label}</option>)}
          </select>
        </label>
        {isMulti && (
          <label>
            Add event
            <select value={batchScenario} onChange={(e) => setBatchScenario(e.target.value)} disabled={disabled}>
              {SINGLE.map((key) => <option key={key} value={key}>{SCENARIOS[key].label}</option>)}
            </select>
          </label>
        )}
        <Scenario
          scenario={active} nodes={nodes} links={links} target={target} disabled={disabled}
          onTarget={(id) => setTargets((prev) => ({ ...prev, [active]: id }))}
          values={values} onValue={(key, value) => setValues((prev) => ({ ...prev, [key]: value }))}
        />
        {hint && <p className="hint invalid">{hint}</p>}
        {isMulti ? (
          <>
            <button
              type="button" className="secondary" disabled={disabled || !valid}
              onClick={() => setBatch((prev) => [...prev, { type: active, ...eventBody() }])}
            >
              Add to batch
            </button>
            {batch.length > 0 && (
              <ul className="batch">
                {batch.map((e, i) => (
                  <li key={i}>
                    <span>{describeQueued(e, nameOf, linkOf)}</span>
                    <button type="button" aria-label="Remove event" onClick={() => setBatch((prev) => prev.filter((_, j) => j !== i))}>×</button>
                  </li>
                ))}
              </ul>
            )}
            <button type="submit" className="chaos-go" disabled={disabled || batch.length === 0}>
              {SCENARIOS.multi_failure.action}{batch.length ? ` (${batch.length})` : ""}
            </button>
          </>
        ) : (
          <button type="submit" className="chaos-go" disabled={disabled || !valid}>{SCENARIOS[scenario].action}</button>
        )}
      </form>
      <p className="hint">
        Chaos changes the real topology. Run a traffic simulation afterwards to see the impact; nothing recovers by itself.
      </p>
    </section>
  );
}

// One line describing what an active event does to its target.
export function describeEvent(e) {
  const p = e.parameters;
  switch (e.scenario) {
    case "router_failure":
    case "link_failure": return "FAILED";
    case "packet_loss": return `Loss: ${p.packet_loss}%`;
    case "latency": return `Latency: ${p.latency} ms`;
    case "bandwidth_reduction": return `Bandwidth: ${p.bandwidth} Mbps`;
    case "congestion":
      return `Congestion: +${p.latency_increase} ms, −${p.bandwidth_reduction_percent}% bandwidth, +${p.packet_loss}% loss`;
    default: return e.scenario;
  }
}

export function ActiveChaosPanel({ active, disabled, onRevert, onReset }) {
  return (
    <section className="panel chaos">
      <h2>Active Chaos</h2>
      {active.length === 0 ? (
        <p className="hint">No active chaos. The network is running as designed.</p>
      ) : (
        <ul className="active-list">
          {active.map((exp) => (
            <li key={exp.experiment_id}>
              <b>{exp.experiment_id}</b> <span className="muted">{exp.name}</span>
              {exp.events.map((e) => (
                <div key={e.event_id} className="active-line">
                  <span>{e.target_label}</span> <span className={e.scenario.endsWith("failure") ? "tag-failed" : "tag-degraded"}>→ {describeEvent(e)}</span>
                </div>
              ))}
              <button type="button" className="secondary" disabled={disabled} onClick={() => onRevert(exp.experiment_id)}>
                Revert Experiment
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="danger" disabled={disabled || active.length === 0} onClick={onReset}>
        RESET ALL CHAOS
      </button>
    </section>
  );
}

const when = (iso) => (iso ? new Date(`${iso}Z`).toLocaleString() : "—"); // the API sends UTC without a suffix

export function ChaosHistory({ history }) {
  return (
    <section className="panel">
      <h2>Chaos History</h2>
      {history.length === 0 ? (
        <p className="hint">No chaos experiments yet.</p>
      ) : (
        <table className="history">
          <thead>
            <tr><th>Experiment</th><th>Scenario</th><th>Target</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.experiment_id}>
                <td>{h.experiment_id}</td>
                <td>{SCENARIOS[h.scenario]?.label ?? h.scenario}</td>
                <td>{h.target === "network" ? `${h.event_count} targets` : h.target_label}</td>
                <td><span className={`badge ${h.status === "active" ? "failed" : "completed"}`}>{h.status}</span></td>
                <td>{when(h.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
