FROM gcc:13-bookworm AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build --target packer_service --parallel 2

FROM debian:bookworm-slim
COPY --from=build /src/build/packer_service /usr/local/bin/packer_service
ENV PACKER_HOST=0.0.0.0
ENV PORT=8090
EXPOSE 8090
CMD ["sh", "-c", "exec /usr/local/bin/packer_service \"${PORT:-8090}\" 0.0.0.0"]
