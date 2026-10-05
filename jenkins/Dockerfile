# Jenkins with Python + Docker CLI so the pipeline can test and build images.
# Runs as root and uses the host Docker socket (fine for a college/lab setup, not for production).
FROM jenkins/jenkins:lts-jdk17
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-pip docker.io curl \
 && rm -rf /var/lib/apt/lists/*
