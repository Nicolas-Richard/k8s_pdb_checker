from kubernetes import client, config
from collections import defaultdict
import logging
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_kubernetes_connection():
    """Test the Kubernetes connection"""
    try:
        v1 = client.CoreV1Api()
        v1.list_namespace()
        return True
    except Exception as e:
        raise Exception(f"Failed to connect to Kubernetes cluster: {str(e)}")


def get_cluster_info():
    """Get current cluster information"""
    try:
        # Get current context first
        current_context = config.list_kube_config_contexts()[1]
        context_name = current_context['name']
        
        # Load full config to get cluster info
        full_config = config.load_kube_config()
        
        # Get cluster info from current context
        cluster_name = current_context.get('context', {}).get('cluster', context_name)
        
        # Get API server from current context's cluster
        k8s_client = client.ApiClient()
        server = k8s_client.configuration.host
        
        return {
            'cluster_name': cluster_name,
            'context_name': context_name,
            'server': server
        }
    except Exception as e:
        logger.error(f"Error getting cluster info: {str(e)}")
        # Return minimal info to allow script to continue
        return {
            'cluster_name': 'unknown',
            'context_name': 'unknown',
            'server': 'unknown'
        }


def get_workloads():
    """Get all deployments, statefulsets, daemonsets, and rollouts"""
    apps_v1 = client.AppsV1Api()
    argoproj_v1alpha1 = client.CustomObjectsApi()

    resources = []

    logger.info("Fetching Deployments...")
    deployments = apps_v1.list_deployment_for_all_namespaces().items
    resources.extend([
        (d.metadata.namespace, d.metadata.name, d.spec.selector.match_labels, "deployment", None)
        for d in deployments
    ])

    logger.info("Fetching StatefulSets...")
    statefulsets = apps_v1.list_stateful_set_for_all_namespaces().items
    resources.extend([
        (s.metadata.namespace, s.metadata.name, s.spec.selector.match_labels, "statefulset", None)
        for s in statefulsets
    ])

    logger.info("Fetching DaemonSets...")
    daemonsets = apps_v1.list_daemon_set_for_all_namespaces().items
    resources.extend([
        (d.metadata.namespace, d.metadata.name, d.spec.selector.match_labels, "daemonset", None)
        for d in daemonsets
    ])

    logger.info("Fetching Argo Rollouts...")
    try:
        rollouts = argoproj_v1alpha1.list_cluster_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            plural="rollouts"
        )
        resources.extend([
            (r['metadata']['namespace'], r['metadata']['name'], r['spec']['selector']['matchLabels'], "rollout", r['spec'].get('replicas', 1))
            for r in rollouts['items']
        ])
    except Exception as e:
        logger.warning(f"Failed to fetch Argo Rollouts: {str(e)}")

    return resources


def get_pdbs():
    """Get all PodDisruptionBudget objects"""
    logger.info("Fetching PDBs...")
    try:
        policy_v1 = client.PolicyV1Api()
        pdbs = policy_v1.list_pod_disruption_budget_for_all_namespaces()
        return pdbs.items
    except Exception as e:
        logger.error(f"Failed to fetch PDBs: {str(e)}")
        return []


def build_pdb_map(pdbs):
    """Create lookup dictionary: namespace -> selector -> pdb_name"""
    pdb_map = defaultdict(dict)

    for pdb in pdbs:
        ns = pdb.metadata.namespace
        try:
            labels = pdb.spec.selector.match_labels
            selector = ','.join(f"{k}={v}" for k, v in sorted(labels.items()))
            pdb_map[ns][selector] = pdb.metadata.name
        except AttributeError:
            logger.warning(f"Skipping malformed PDB: {pdb.metadata.name} in {ns}")
            continue

    return pdb_map


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Check Kubernetes workloads for missing PDBs')
    parser.add_argument('--hide-pdb', action='store_true', help='Hide workloads that have PDBs')
    parser.add_argument('--hide-zero-replicas', action='store_true', help='Hide workloads with zero replicas')
    args = parser.parse_args()

    # Load kubeconfig and log cluster info
    try:
        logger.info("Loading kubeconfig...")
        config.load_kube_config()
        logger.info("Successfully loaded kubeconfig")

        # Test connection before proceeding
        logger.info("Testing Kubernetes connection...")
        test_kubernetes_connection()
        logger.info("Successfully connected to Kubernetes cluster")

        # Get cluster info
        cluster_info = get_cluster_info()
        if cluster_info['cluster_name'] != 'unknown':
            logger.info(
                f"Connected to cluster: {cluster_info['cluster_name']}\n"
                f"API Server: {cluster_info['server']}\n"
                f"Using context: {cluster_info['context_name']}"
            )
    except Exception as e:
        logger.error(f"Failed to load kubeconfig: {str(e)}")
        logger.error("Please ensure you have a valid kubeconfig file")
        return

    # Get all resources
    try:
        workloads = get_workloads()
        pdbs = get_pdbs()
    except Exception as e:
        logger.error(f"Failed to fetch cluster resources: {str(e)}")
        return

    # Build PDB lookup map
    pdb_map = build_pdb_map(pdbs)

    # Analyze workloads
    missing = []
    existing = []

    for ns, name, labels, workload_type, replicas in workloads:
        # Skip workloads with zero replicas if --hide-zero-replicas is set
        if args.hide_zero_replicas and replicas == 0:
            continue

        # Sort labels to ensure consistent ordering for comparison
        # This makes the selector string predictable and helps with debugging
        sorted_labels = sorted(labels.items())
        
        # Join labels with commas to create a unique identifier for the label set
        # This format matches how Kubernetes displays selectors and makes it easy to
        # understand which labels need to be matched when creating a PDB
        selector = ','.join(f"{k}={v}" for k, v in sorted_labels)

        if selector in pdb_map.get(ns, {}):
            existing.append((ns, name, pdb_map[ns][selector], workload_type, replicas))
        else:
            missing.append((ns, name, selector, workload_type, replicas))

    # Print results
    if not args.hide_pdb:
        logger.info("\nWorkloads with PDBs:")
        for ns, name, pdb_name, workload_type, _ in existing:
            logger.info(f"✅ {ns}/{name} ({workload_type}) -> {pdb_name}")

    logger.info("\nWorkloads without PDBs:")
    for ns, name, selector, workload_type, replicas in missing:
        if workload_type == "rollout":
            logger.info(f"❌ {ns}/{name} ({workload_type}) - Replicas: {replicas} (selector: {selector})")
        else:
            logger.info(f"❌ {ns}/{name} ({workload_type}) (selector: {selector})")

    total_workloads = len(existing) + len(missing)
    logger.info(f"\nSummary: {len(existing)} with PDBs, {len(missing)} without (Total: {total_workloads})")


if __name__ == '__main__':
    main()

