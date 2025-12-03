#!/bin/bash

# Build the Docker image
podman build -f Dockerfile.svfr -t svfr-base:latest .

# Tag it for your registry
podman tag svfr-base:latest sgs-registry.snucse.org/ws-7l3atgjy3al41/svfr-base:latest

# Push to registry
podman push sgs-registry.snucse.org/ws-7l3atgjy3al41/svfr-base:latest
