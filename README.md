# Kubernetes PDB Checker

A Python script to identify Kubernetes workloads that lack Pod Disruption Budgets (PDBs).

## Purpose

This tool helps maintain high availability in your Kubernetes clusters by identifying workloads (Deployments, StatefulSets, DaemonSets, and Argo Rollouts) that don't have PDBs configured. PDBs are crucial for ensuring controlled pod eviction during cluster maintenance or node failures.

## Requirements

- Python 3.9+
- Kubernetes Python client (`pip install kubernetes`)
- Valid kubeconfig file

## Usage

1. Ensure your kubeconfig is properly configured:
   ```bash
   kubectl config current-context
   ```

2. Run the script:
   ```bash
   python main.py
   ```

## About Label Matching

### What are match_labels?
- Key-value pairs that define which pods a workload (like a Deployment) manages
- Example: `{"app": "frontend", "tier": "web"}`

### Why are they important for PDBs?
- PDBs work by matching pods using label selectors
- A PDB must target the same pods that the workload manages
- If the labels don't match, the PDB won't protect the workload's pods

### Example
```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
spec:
  selector:
    matchLabels:
      app: frontend
      tier: web
  template:
    metadata:
      labels:
        app: frontend
        tier: web
    spec:
      containers:
      - name: nginx
        image: nginx

# PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: frontend-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: frontend
      tier: web  # Must match the Deployment's labels
```

## Output

The script will display:
- Workloads with existing PDBs (✅)
- Workloads missing PDBs (❌)
- The label selectors needed for creating PDBs
- A summary of PDB coverage

## Example Output

```
Workloads with PDBs:
✅ ns1/app1 -> pdb1

Workloads without PDBs:
❌ ns3/app3 (selector: app=app3,tier=web)
❌ ns4/app4 (selector: app=app4,environment=prod)

Summary: 1 with PDBs, 2 without
```

The `selector` in the output shows the exact labels that need to be matched when creating a PDB for the workload. 