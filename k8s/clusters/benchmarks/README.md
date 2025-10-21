# Benchmark Cluster Infrastructure

This directory contains Kubernetes manifests for the benchmark cluster's logging infrastructure.

## Overview

### Vector Log Collection

Vector is deployed as a distributed logging system to collect logs from Codex benchmark experiments:

**Vector Agent (DaemonSet):**
- Collects logs from benchmark pods (filtered by label: `app.kubernetes.io/name=codex-benchmarks`)
- Forwards compressed logs to Vector Aggregator via port 6000

**Vector Aggregator:**
- Receives logs from all Vector agents
- Writes consolidated logs to PVC as JSONL files: `/vector-logs/benchmarks-YYYY-MM-DD.jsonl`
- Used by log-parsing Argo workflow for post-experiment processing

**Persistent Volume:**
- Stores collected JSONL logs
- Mounted by Vector Aggregator and log-parsing workflow
- Allows logs to persist between workflow runs

**S3 Secret:**
- Credentials for uploading processed logs to S3-compatible storage
- Used by log-parsing workflow's tar-and-upload step

**RBAC:**
- Service account and cluster role for Vector to access Kubernetes API
- Required for reading pod logs cluster-wide

## Installation Order

### 1. Create namespace (if not exists)

```bash
kubectl create namespace argo
```

### 2. Apply Vector components

```bash
kubectl apply -f vector/vector-pvc.yaml -n argo
kubectl apply -f vector/vector-agent-configmap.yaml -n argo
kubectl apply -f vector/vector-configmap.yaml -n argo
kubectl apply -f vector/vector-aggregator-configmap.yaml -n argo
kubectl apply -f vector/vector-deployment.yaml -n argo
kubectl apply -f vector/vector-aggregator-deployment.yaml -n argo
```

### 3. Configure S3 access

```bash
# Edit s3-secret.yaml with your credentials first
kubectl apply -f s3-secret.yaml -n argo
```

### 4. Configure Vector RBAC

```bash
kubectl apply -f vector/vector-aggregator-rbac.yaml -n argo
```

## Verification

### Check Vector Agent status
```bash
kubectl get daemonset -n argo | grep vector
kubectl get pods -n argo -l app.kubernetes.io/name=vector
```

### Check Vector Aggregator status
```bash
kubectl get deployment -n argo | grep vector-aggregator
```

### Check PVC status
```bash
kubectl get pvc -n argo vector-logs-pvc
```

## Troubleshooting

### Vector Agent not collecting logs
- Verify pod labels: `kubectl get pods -n codex-benchmarks --show-labels`
- Check agent logs: `kubectl logs -n argo -l app.kubernetes.io/name=vector`
- Ensure RBAC is applied: `kubectl get clusterrole vector-agent`

### Logs not appearing in PVC
- Check aggregator connection: `kubectl logs -n argo deployment/vector-aggregator | grep error`
- Verify PVC is mounted: `kubectl describe pod -n argo <aggregator-pod>`

### S3 upload failures
- Verify secret exists: `kubectl get secret -n argo s3-codex-benchmarks`
- Check credentials are correct (not placeholders)
