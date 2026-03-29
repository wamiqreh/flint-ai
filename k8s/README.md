# Kubernetes Manifests

This folder contains manifests for deploying the API and Worker to Kubernetes.

## Manifests

| File                    | Description                                      |
|-------------------------|--------------------------------------------------|
| `configmap.yaml`        | Environment configuration                        |
| `secret.example.yaml`   | Secret template (replace values before applying)  |
| `api-deployment.yaml`   | API server Deployment (2 replicas)                |
| `api-service.yaml`      | ClusterIP Service for the API                     |
| `worker-deployment.yaml` | Worker Deployment                                |
| `ingress.yaml`          | Ingress with TLS (requires nginx + cert-manager)  |
| `hpa.yaml`              | Horizontal Pod Autoscaler for API and Worker      |
| `pdb.yaml`              | Pod Disruption Budgets for rolling updates        |

## Apply

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.example.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/pdb.yaml
```

Replace `secret.example.yaml` values before applying to non-local environments.

## Prerequisites

- **Ingress**: Requires an [nginx ingress controller](https://kubernetes.github.io/ingress-nginx/)
  and [cert-manager](https://cert-manager.io/) for automatic TLS.
- **HPA**: Requires [metrics-server](https://github.com/kubernetes-sigs/metrics-server).
- Update the `host` in `ingress.yaml` to match your domain.
