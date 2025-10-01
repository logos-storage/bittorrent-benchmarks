FROM bitnamilegacy/kubectl:1.31.1 AS kubectl

FROM python:3.12-slim

COPY --from=kubectl /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl

RUN apt-get update && apt-get install -y curl

RUN curl -SL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
RUN chmod 700 get_helm.sh
RUN ./get_helm.sh

RUN curl -SL "https://dl.min.io/client/mc/release/linux-$(dpkg --print-architecture)/mc" \
    --create-dirs \
    -o /usr/local/bin/mc && \
    chmod +x /usr/local/bin/mc

RUN mkdir /opt/bittorrent-benchmarks
WORKDIR /opt/bittorrent-benchmarks

COPY ./k8s ./k8s
COPY ./docker ./docker
COPY ./benchmarks/k8s/parameter_expander.py .
