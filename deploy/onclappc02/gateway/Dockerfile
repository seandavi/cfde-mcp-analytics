# Official agentgateway v1.6.0 image (distroless, no shell) plus a static busybox, so the access
# log on stdout can be appended to a file Vector tails. agentgateway has no file log output.
FROM busybox:1.37.0-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092 AS busybox
FROM ghcr.io/agentgateway/agentgateway:v1.6.0@sha256:9d3e6044ddcdc0878b1787f77bd401252b95e22684203fb5e874c4c42d2ed90c
COPY --from=busybox /bin/busybox /bin/busybox
# stdout (JSON log lines, one per request plus a few startup lines) -> file; stderr stays on
# `docker logs`. O_APPEND (>>) so host logrotate can copytruncate safely.
ENTRYPOINT ["/bin/busybox", "sh", "-c", "exec /app/agentgateway -f /etc/agentgateway/config.yaml >> /logs/gateway.log"]
