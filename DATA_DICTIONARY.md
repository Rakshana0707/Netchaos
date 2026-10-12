# Research Data Dictionary

This dictionary defines every feature present in the NetChaos Module 12 Research Dataset.

## Identification
- **dataset_id** (string): Unique identifier for the dataset.
- **dataset_version** (string): Semantic version for dataset schema/configuration used at generation.
- **experiment_id** (string): Internal ID referencing the source Module 7 tracking run.
- **run_id** (string, nullable): Module 11 batch run ID if this row was auto-generated.
- **plan_id** (string, nullable): Module 11 plan ID representing the sweep configuration.
- **network_id** (string): Topology target against which this experiment executed.

## Topology
- **topology_type** (string): Sourced from Network structure. Default `unknown`.
- **node_count** (int): Total static topology nodes.
- **link_count** (int): Total static topology links.

## Traffic
- **source_node** (string, nullable): Request origin router.
- **destination_node** (string, nullable): Destination target router.
- **packet_count** (int, nullable): Total payload chunks requested natively by system.
- **packet_size** (int, nullable): Size per packet frame (bytes).
- **delivered_packets** (int, nullable): Packets succeeding delivery on final sim run.
- **dropped_packets** (int, nullable): Packets lost/discarded natively without retransmit.
- **packet_loss_percentage** (float, nullable): (dropped / packet_count) * 100.
- **baseline_latency** (float, nullable): Native path baseline RTT measured (ms).
- **chaos_latency** (float, nullable): Direct degraded simulation measured RTT (ms).
- **recovered_latency** (float, nullable): Found alternative route recovered average RTT (ms).
- **baseline_throughput** (float, nullable): Pre-chaos successful capacity.
- **chaos_throughput** (float, nullable): Capacity strictly available during chaos.
- **recovered_throughput** (float, nullable): Output post-recovery capacities.

## Chaos
- **chaos_type** (string, nullable): Injection method (e.g. `link_failure`, `router_failure`, `packet_loss`).
- **chaos_target** (string, nullable): Link or Node targeted natively by system.
- **chaos_severity** (string, nullable): Native magnitude mapping representation. 
- **packet_loss_injected** (float, nullable): Direct configuration for packet loss event magnitude.
- **latency_injected** (float, nullable): Configuration logic defining ms increases.
- **bandwidth_reduction** (float, nullable): Simulated output bandwidth reductions dynamically.
- **multiple_failure_count** (int): Iterative count marking arrays of failure.

## Failure Detection
- **failure_detected** (bool): Did the diagnostic service identify anomalies.
- **failed_node_count** (int): Total down vertices.
- **failed_link_count** (int): Total broken edge paths.
- **degraded_link_count** (int): QoS impacting elements globally observed.
- **affected_traffic_count** (int): Stream routes passing degraded environments.
- **partition_count** (int): Separated network components natively.
- **connectivity_before** (int, nullable): Available path combinations purely pre-chaos.
- **connectivity_after_failure** (int, nullable): Post-anomaly paths remaining active.
- **failure_severity** (string, nullable): High-level system severity marker mapping.

## Recovery
- **recovery_attempted** (bool): Dynamic Recovery Service triggered?
- **recovery_outcome** (string): Values: `RECOVERED`, `PARTIALLY_RECOVERED`, `UNRECOVERABLE`, `NOT_ATTEMPTED`.
- **original_route_length** (int, nullable): Baseline flow path complexity natively structured.
- **recovered_route_length** (int, nullable): Alternative routes chosen natively structured.
- **route_changed** (bool, nullable): True if path shifted logically on failure triggers.
- **recovery_time** (float, nullable): Time (seconds) algorithm computed new path states.

## Resilience (Module 10 Derived Metrics)
- **latency_degradation_percentage** (float, nullable): Percentage delta logic mapping vs baseline. 
- **packet_loss_degradation_percentage** (float, nullable): Derived metric indicating stream disruptions natively.
- **throughput_degradation_percentage** (float, nullable): Loss capacities metrics mapping natively.
- **connectivity_preservation** (float, nullable): Percentage ratio paths maintained globally. 
- **performance_preservation** (float, nullable): QoS structural maintaining ratio.
- **recovery_effectiveness** (float, nullable): Dynamic structural return percentage values natively.
- **impact_score** (float, nullable): Severity magnitude derived score across chaos.
- **resilience_score** (float, nullable): Ultimate overarching dataset structural rating natively scored.

## Dataset Quality
- **data_quality** (string): Flags system state integrity mapping internally (`VALID`, `PARTIAL`, `INVALID`).
- **validation_warnings** (array): String metrics pointing at anomalies.
