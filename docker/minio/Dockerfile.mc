# MinIO client, built from the official Community source release; minio-init uses it to create the bucket and the
# application's own user and policy. Same recipe as document_manager (docs/NGUON_GOC.md).
FROM golang:1.24-bookworm AS build
RUN CGO_ENABLED=0 go install github.com/minio/mc@RELEASE.2025-08-13T08-35-41Z

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /go/bin/mc /usr/local/bin/mc
ENTRYPOINT ["mc"]
