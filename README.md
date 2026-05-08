# PII models in Docker

This project contains PII models in Docker.

The project uses docker-compose to orchestrate the services for development environment.

In production, we use Kubernetes with Helm manifests.

## Terms

* Personally Identifiable Information (PII)
* Protected Health Information (PHI)
* Payment Card Industry (PCI)

## Architecture Ideas

![architecture](./images/architecture.drawio.svg)

### Other architecture ideas

* Architecture 1

![architecture](./images/pii_model_k8s_architecture.svg)

* Architecture 2

![architecture](./images/kong_auth_model_routing_flow.svg)
