ARG MATRIX_MDAD_RUNNER_BASE_IMAGE
ARG MATRIX_MDAD_RUNNER_BASE_VERSION
ARG MATRIX_MDAD_RUNNER_DOCKER_CLI_IMAGE
ARG MATRIX_MDAD_RUNNER_DOCKER_CLI_VERSION
FROM ${MATRIX_MDAD_RUNNER_DOCKER_CLI_IMAGE}:${MATRIX_MDAD_RUNNER_DOCKER_CLI_VERSION} AS docker-cli

FROM ${MATRIX_MDAD_RUNNER_BASE_IMAGE}:${MATRIX_MDAD_RUNNER_BASE_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/ansible \
    PATH=/opt/ansible/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY --from=docker-cli /usr/local/bin/docker /usr/bin/docker

RUN rm -rf /var/lib/apt/lists/* \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      dbus \
      git \
      openssh-client \
      python3-venv \
      systemd \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV" \
 && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir \
      'ansible-core>=2.18,<2.19' \
      docker \
      jmespath \
      netaddr \
      passlib \
      pyyaml \
      requests

RUN ansible-galaxy collection install \
      community.docker \
      community.general \
      ansible.posix

WORKDIR /mdad
