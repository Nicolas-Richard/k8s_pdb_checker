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

## Output

The script will display:
- Workloads with existing PDBs (✅)
- Workloads missing PDBs (❌)
- A summary of PDB coverage

## Example Output

```
Workloads with PDBs:
✅ ns1/app1 -> pdb1
✅ ns2/app2 -> pdb2

Workloads without PDBs:
❌ ns3/app3 (selector: app=app3)
❌ ns4/app4 (selector: app=app4)

Summary: 2 with PDBs, 2 without
``` 