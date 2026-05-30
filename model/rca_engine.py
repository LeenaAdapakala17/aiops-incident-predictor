"""
RCA Engine — rule-based root cause analysis + remediation steps.
Called after ML prediction to explain WHY and WHAT TO DO.
"""
import pandas as pd

# ── RCA rules per domain ───────────────────────────────────────────────────────
# Each rule: (condition_fn, incident_type, root_cause, impact, solutions, kubectl_or_az_commands)

RULES = {
    "kubernetes": [
        {
            "check":   lambda r: r.get("oom_events", 0) > 0,
            "type":    "OOMKill",
            "cause":   "Pod is consuming more memory than its configured limit. Kubernetes OOM killer is terminating the container.",
            "impact":  "Service restarts cause request drops, potential data loss, and degraded availability.",
            "solutions": [
                "Increase memory limit in the pod spec (resources.limits.memory)",
                "Profile the application for memory leaks using heap dumps",
                "Add Vertical Pod Autoscaler (VPA) to auto-tune resource requests",
                "Review recent code deployments that may have introduced memory-heavy operations",
            ],
            "commands": [
                "kubectl describe pod <pod-name> -n <namespace>",
                "kubectl top pod <pod-name> -n <namespace>",
                "kubectl get events --field-selector reason=OOMKilling -n <namespace>",
                "kubectl edit deployment <deployment-name> -n <namespace>  # increase limits",
            ],
        },
        {
            "check":   lambda r: r.get("restart_count_5m", 0) > 4,
            "type":    "CrashLoopBackOff",
            "cause":   "Container is repeatedly crashing and being restarted. Kubernetes backs off the restart interval exponentially.",
            "impact":  "Service is effectively unavailable. Each crash may corrupt in-flight requests.",
            "solutions": [
                "Check application logs for the crash reason (exception, missing config, port conflict)",
                "Verify environment variables and secrets are correctly mounted",
                "Check liveness probe configuration — misconfigured probes trigger false restarts",
                "Roll back to the last stable deployment if crash started after a release",
            ],
            "commands": [
                "kubectl logs <pod-name> -n <namespace> --previous",
                "kubectl describe pod <pod-name> -n <namespace>",
                "kubectl rollout history deployment/<name> -n <namespace>",
                "kubectl rollout undo deployment/<name> -n <namespace>",
            ],
        },
        {
            "check":   lambda r: r.get("mem_limit_ratio", 0) > 0.88,
            "type":    "Memory Pressure",
            "cause":   "Pod memory usage is approaching or exceeding its limit. OOMKill is imminent.",
            "impact":  "If not addressed within minutes, the pod will be killed and restarted, causing service disruption.",
            "solutions": [
                "Immediately increase memory limit to buy time: kubectl set resources",
                "Trigger a rolling restart to clear accumulated memory state",
                "Enable HPA to distribute load across more replicas",
                "Investigate heap growth trend in APM/Grafana",
            ],
            "commands": [
                "kubectl top pods -n <namespace> --sort-by=memory",
                "kubectl set resources deployment/<name> --limits=memory=2Gi -n <namespace>",
                "kubectl scale deployment/<name> --replicas=<n+1> -n <namespace>",
                "kubectl rollout restart deployment/<name> -n <namespace>",
            ],
        },
        {
            "check":   lambda r: r.get("cpu_throttle_rate_pct", 0) > 60,
            "type":    "CPU Throttling",
            "cause":   "cgroup CPU limits are throttling the container. The pod is being artificially slowed down.",
            "impact":  "Increased latency, slow response times, and potential timeout errors for downstream services.",
            "solutions": [
                "Increase CPU limit in the deployment spec",
                "Optimise application CPU-intensive code paths (profiling)",
                "Consider moving CPU-heavy workloads to dedicated node pools",
                "Review if batch jobs are competing with serving workloads",
            ],
            "commands": [
                "kubectl top pod <pod-name> -n <namespace>",
                "kubectl set resources deployment/<name> --limits=cpu=2000m -n <namespace>",
                "kubectl get hpa -n <namespace>",
            ],
        },
        {
            "check":   lambda r: r.get("pending_time_sec", 0) > 60,
            "type":    "Pod Stuck Pending",
            "cause":   "Pod cannot be scheduled — insufficient cluster capacity, node selector mismatch, or taint/toleration issue.",
            "impact":  "New pods are not starting, scaling events are failing silently.",
            "solutions": [
                "Check node capacity and add nodes to the node pool if needed",
                "Review node selectors and affinity rules in the pod spec",
                "Check for taints on nodes that the pod does not tolerate",
                "Review AKS cluster autoscaler logs",
            ],
            "commands": [
                "kubectl describe pod <pod-name> -n <namespace>  # check Events section",
                "kubectl get nodes -o wide",
                "kubectl describe nodes | grep -A5 Taints",
                "az aks nodepool scale --cluster-name <cluster> --name <pool> --node-count <n>",
            ],
        },
    ],

    "cloud": [
        {
            "check":   lambda r: r.get("cpu_usage_pct", 0) > 88,
            "type":    "CPU Exhaustion",
            "cause":   "Azure VM CPU utilisation is critically high. The VM is unable to process workloads at expected throughput.",
            "impact":  "Application slowdowns, request timeouts, and potential VM unresponsiveness.",
            "solutions": [
                "Scale up VM to a larger SKU (e.g. Standard_D4s_v3 → Standard_D8s_v3)",
                "Enable Azure VM Scale Sets autoscaling",
                "Identify CPU-heavy processes using Azure Monitor Metrics",
                "Distribute workload across multiple VMs via Load Balancer",
            ],
            "commands": [
                "az vm list-usage --location <region>",
                "az monitor metrics list --resource <vm-id> --metric 'Percentage CPU'",
                "az vm resize --resource-group <rg> --name <vm> --size Standard_D8s_v3",
                "az vmss scale --new-capacity <n> --name <vmss> --resource-group <rg>",
            ],
        },
        {
            "check":   lambda r: r.get("memory_usage_pct", 0) > 90,
            "type":    "Memory Exhaustion",
            "cause":   "VM memory is nearly full. OS will begin swapping to disk, causing severe performance degradation.",
            "impact":  "Extreme slowdown, potential OOM kills of processes, VM may become unresponsive.",
            "solutions": [
                "Scale VM to memory-optimised SKU (Esv3 or Mv2 series)",
                "Identify memory-heavy processes and restart or tune them",
                "Add swap space as a temporary measure",
                "Review application memory configuration (JVM heap, buffer pools)",
            ],
            "commands": [
                "az monitor metrics list --resource <vm-id> --metric 'Available Memory Bytes'",
                "az vm resize --resource-group <rg> --name <vm> --size Standard_E8s_v3",
            ],
        },
        {
            "check":   lambda r: r.get("disk_iops_pct", 0) > 85 or r.get("storage_throttle", 0) == 1,
            "type":    "Disk IOPS Throttling",
            "cause":   "Azure managed disk IOPS limit has been reached. Storage requests are being queued or rejected.",
            "impact":  "Database slowdowns, write failures, application timeouts on any disk I/O operation.",
            "solutions": [
                "Upgrade disk tier from Standard HDD → Premium SSD → Ultra Disk",
                "Enable Azure disk bursting for temporary IOPS boost",
                "Distribute I/O across multiple disks using striping",
                "Move read-heavy workloads to Azure Cache for Redis",
            ],
            "commands": [
                "az disk update --resource-group <rg> --name <disk> --sku Premium_LRS",
                "az monitor metrics list --resource <disk-id> --metric 'Disk Read Operations/Sec'",
            ],
        },
        {
            "check":   lambda r: r.get("quota_used_pct", 0) > 93,
            "type":    "Quota Breach",
            "cause":   "Azure subscription quota for this resource type is nearly exhausted. New resource creation will fail.",
            "impact":  "Scale-out operations, new deployments, and autoscaling events will fail silently.",
            "solutions": [
                "Request quota increase via Azure Portal (Subscriptions → Usage + Quotas)",
                "Delete unused resources to free quota",
                "Distribute workloads across multiple Azure regions",
                "Use Azure Policy to enforce resource tagging and lifecycle management",
            ],
            "commands": [
                "az vm list-usage --location <region> --output table",
                "az quota show --resource-name <resource> --scope /subscriptions/<id>",
            ],
        },
    ],

    "network": [
        {
            "check":   lambda r: r.get("latency_ms", 0) > 900,
            "type":    "High Latency",
            "cause":   "Network round-trip time is critically elevated. Likely causes: network congestion, distant routing, or overloaded backend.",
            "impact":  "User-facing timeouts, SLA breaches, cascading failures in synchronous service chains.",
            "solutions": [
                "Check Azure Network Watcher for routing anomalies",
                "Enable Azure CDN or Front Door for geographic latency reduction",
                "Review backend service response times — latency may be application-side",
                "Check for noisy-neighbour VMs on the same physical host",
                "Implement circuit breakers to prevent cascade failures",
            ],
            "commands": [
                "az network watcher test-connectivity --source-resource <vm> --dest-address <ip>",
                "kubectl exec -it <pod> -- curl -w '%{time_total}' -o /dev/null <service-url>",
            ],
        },
        {
            "check":   lambda r: r.get("packet_loss_pct", 0) > 4,
            "type":    "Packet Loss",
            "cause":   "Significant packet loss detected. Network infrastructure or NIC is dropping packets, forcing TCP retransmissions.",
            "impact":  "TCP connections degrade severely. Even 5% packet loss can halve throughput and triple latency.",
            "solutions": [
                "Run Azure Network Watcher packet capture to identify drop location",
                "Check NIC driver and firmware on affected VMs",
                "Review NSG rules for inadvertent traffic blocking",
                "Check for MTU mismatch causing fragmentation and drops",
                "Failover to a secondary network path or availability zone",
            ],
            "commands": [
                "az network watcher packet-capture create --resource-group <rg> --vm <vm>",
                "az network watcher show-topology --resource-group <rg>",
                "kubectl exec -it <pod> -- ping -c 100 <destination>",
            ],
        },
        {
            "check":   lambda r: r.get("dns_failures_5m", 0) > 2,
            "type":    "DNS Failures",
            "cause":   "DNS resolution is failing. CoreDNS in AKS may be overloaded, or upstream DNS is unreachable.",
            "impact":  "Services cannot discover each other by name. All service-to-service communication fails.",
            "solutions": [
                "Check CoreDNS pod health in the kube-system namespace",
                "Scale up CoreDNS replicas if under load",
                "Review CoreDNS ConfigMap for misconfiguration",
                "Check Azure Private DNS zone linkage to the VNet",
                "Add DNS caching at the application layer (nscd or dnsmasq)",
            ],
            "commands": [
                "kubectl get pods -n kube-system -l k8s-app=kube-dns",
                "kubectl logs -n kube-system -l k8s-app=kube-dns",
                "kubectl scale deployment coredns -n kube-system --replicas=4",
                "kubectl exec -it <pod> -- nslookup kubernetes.default",
            ],
        },
        {
            "check":   lambda r: r.get("ingress_saturation_pct", 0) > 88,
            "type":    "Ingress Saturation",
            "cause":   "AKS Ingress controller or Azure Load Balancer is at capacity. New connections are being queued or dropped.",
            "impact":  "New incoming requests fail or time out. Existing connections may also degrade.",
            "solutions": [
                "Scale ingress controller replicas horizontally",
                "Upgrade Azure Load Balancer SKU to Standard if on Basic",
                "Enable AGIC (Application Gateway Ingress Controller) for auto-scaling ingress",
                "Implement rate limiting to protect against traffic spikes",
                "Add HPA to ingress controller deployment",
            ],
            "commands": [
                "kubectl scale deployment ingress-nginx-controller -n ingress-nginx --replicas=4",
                "kubectl get hpa -n ingress-nginx",
                "az network lb show --resource-group <rg> --name <lb-name>",
            ],
        },
    ],

    "application": [
        {
            "check":   lambda r: r.get("error_rate_5xx_pct", 0) > 8,
            "type":    "High Error Rate",
            "cause":   "Server-side error rate is critically high. Upstream dependency failure, unhandled exceptions, or deployment regression.",
            "impact":  "Users are experiencing failures. Revenue impact if payment or core flows are affected.",
            "solutions": [
                "Check application logs for exception stack traces",
                "Verify all upstream dependencies (DB, cache, APIs) are healthy",
                "Roll back the latest deployment if error rate spiked post-release",
                "Enable circuit breaker pattern to fail fast and protect downstream",
                "Check for database connection pool exhaustion",
            ],
            "commands": [
                "kubectl logs <pod-name> -n <namespace> --tail=200 | grep ERROR",
                "kubectl rollout undo deployment/<name> -n <namespace>",
                "kubectl exec -it <pod> -- curl -v http://localhost:<port>/health",
            ],
        },
        {
            "check":   lambda r: r.get("response_time_p99_ms", 0) > 2500,
            "type":    "Slow Response (P99)",
            "cause":   "99th percentile response time is critically slow. Worst-case users are experiencing multi-second delays.",
            "impact":  "SLA breach likely. Users at the tail of the distribution are effectively experiencing an outage.",
            "solutions": [
                "Profile slow endpoints with APM (Application Insights, Datadog)",
                "Check for slow database queries — add indexes or optimise queries",
                "Review thread pool size and connection pool configuration",
                "Enable async processing for non-critical operations",
                "Add caching layer (Redis) for frequently accessed data",
            ],
            "commands": [
                "kubectl exec -it <pod> -- curl -w '%{time_total}' -o /dev/null http://localhost/api/health",
                "kubectl top pods -n <namespace>",
            ],
        },
        {
            "check":   lambda r: r.get("heap_usage_pct", 0) > 88,
            "type":    "Memory Leak",
            "cause":   "Application heap memory is critically high and not being reclaimed by GC. A memory leak is likely.",
            "impact":  "Without intervention, the application will crash with OutOfMemoryError, causing full service outage.",
            "solutions": [
                "Take a heap dump immediately for offline analysis",
                "Trigger a rolling restart now to restore service while investigating",
                "Use async profiler or Java Flight Recorder to identify leak source",
                "Review recent code changes for unbounded caches or unclosed resources",
                "Increase JVM heap as a temporary measure: -Xmx",
            ],
            "commands": [
                "kubectl exec -it <pod> -- jmap -dump:format=b,file=/tmp/heap.bin <pid>",
                "kubectl rollout restart deployment/<name> -n <namespace>",
                "kubectl set env deployment/<name> JAVA_OPTS='-Xmx4g' -n <namespace>",
            ],
        },
        {
            "check":   lambda r: r.get("thread_pool_active_pct", 0) > 87,
            "type":    "Thread Pool Exhaustion",
            "cause":   "Application thread pool is nearly full. Slow downstream calls are holding threads, blocking new requests.",
            "impact":  "New requests queue up and eventually time out. Service appears hung from the outside.",
            "solutions": [
                "Identify which downstream calls are blocking threads (APM trace analysis)",
                "Add timeouts to all outbound HTTP/DB calls",
                "Switch to reactive/async programming model for I/O-bound operations",
                "Increase thread pool size as a temporary measure",
                "Add bulkhead pattern to isolate thread pools per dependency",
            ],
            "commands": [
                "kubectl exec -it <pod> -- jstack <pid> | grep -A3 BLOCKED",
                "kubectl logs <pod> -n <namespace> | grep 'timeout\\|thread'",
            ],
        },
    ],
}

def get_rca(domain: str, row: dict) -> dict:
    """
    Given a domain and a metric row, return the most severe matching RCA.
    Returns dict with: type, cause, impact, solutions, commands
    """
    domain_rules = RULES.get(domain, [])
    matched = []
    for rule in domain_rules:
        try:
            if rule["check"](row):
                matched.append(rule)
        except Exception:
            continue

    if not matched:
        return {
            "type":      "Anomaly Detected",
            "cause":     "Metrics are elevated but no single root cause threshold was breached. Monitor closely.",
            "impact":    "Potential degradation if trend continues.",
            "solutions": ["Continue monitoring", "Review metric trends over the next 15 minutes"],
            "commands":  [],
        }

    # Return the first (highest priority) match
    r = matched[0]
    return {
        "type":      r["type"],
        "cause":     r["cause"],
        "impact":    r["impact"],
        "solutions": r["solutions"],
        "commands":  r["commands"],
    }

def _fill_entity(cmd: str, entity: str, domain: str) -> str:
    """Replace generic placeholders with the actual entity name."""
    # Kubernetes placeholders
    cmd = cmd.replace("<pod-name>", entity)
    cmd = cmd.replace("<deployment-name>", entity)
    cmd = cmd.replace("<name>", entity)
    cmd = cmd.replace("<namespace>", _guess_namespace(entity))
    # Cloud placeholders
    cmd = cmd.replace("<vm>", entity)
    cmd = cmd.replace("<vm-name>", entity)
    # Generic
    cmd = cmd.replace("<service>", entity)
    cmd = cmd.replace("<cluster>", "aks-prod-cluster")
    cmd = cmd.replace("<rg>", "rg-production")
    cmd = cmd.replace("<region>", "westeurope")
    return cmd

def _guess_namespace(entity: str) -> str:
    """Infer likely namespace from entity name."""
    if any(x in entity for x in ["monitor", "prometheus", "grafana", "elastic"]):
        return "monitoring"
    if any(x in entity for x in ["staging", "test", "dev"]):
        return "staging"
    return "production"

def enrich_with_rca(domain: str, df: pd.DataFrame) -> pd.DataFrame:
    """Add rca_type, rca_cause, rca_impact, rca_solutions, rca_commands columns to a scored DataFrame."""
    rows_dicts = df.to_dict(orient="records")
    rcas = [get_rca(domain, row) for row in rows_dicts]
    df = df.copy()
    df["rca_type"]      = [r["type"]                  for r in rcas]
    df["rca_cause"]     = [r["cause"]                 for r in rcas]
    df["rca_impact"]    = [r["impact"]                for r in rcas]
    df["rca_solutions"] = ["§§§".join(r["solutions"]) for r in rcas]
    # Fill entity name into every command
    filled_cmds = []
    for row_dict, rca in zip(rows_dicts, rcas):
        entity = row_dict.get("entity", "unknown")
        filled = [_fill_entity(cmd, entity, domain) for cmd in rca["commands"]]
        filled_cmds.append("§§§".join(filled))
    df["rca_commands"] = filled_cmds
    return df
