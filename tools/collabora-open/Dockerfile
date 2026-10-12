ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG RUNTIME_PACKAGES
ARG SOURCE_URL
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source=$SOURCE_URL \
      org.opencontainers.image.revision=$SOURCE_REVISION \
      org.opencontainers.image.licenses="MPL-2.0"
ENV LC_CTYPE=C.UTF-8
COPY packages/ /tmp/editor-packages/
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${RUNTIME_PACKAGES} /tmp/editor-packages/*.deb \
    && rm -rf /tmp/editor-packages /var/lib/apt/lists/* \
    && coolconfig update-system-template \
    && install -d -o cool -g cool /opt/cool/child-roots /opt/cool/cache \
    && chown -R cool:cool /etc/coolwsd
COPY entrypoint.sh /usr/local/bin/editor-entrypoint
RUN chmod 0755 /usr/local/bin/editor-entrypoint
USER cool
ENTRYPOINT ["/usr/local/bin/editor-entrypoint"]
