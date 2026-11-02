FROM golang:1.24-bookworm AS build
ARG MC_REF=RELEASE.2025-04-16T18-13-26Z
RUN git clone --depth 1 --branch "$MC_REF" https://github.com/minio/mc.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /out/mc .
FROM debian:bookworm-slim
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /src/LICENSE /usr/share/doc/mc/LICENSE
COPY --from=build /out/mc /usr/local/bin/mc
ENTRYPOINT ["mc"]
