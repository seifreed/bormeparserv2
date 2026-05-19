FROM python:3.13-bookworm as builder

RUN mkdir /build
COPY . /build
WORKDIR /build

RUN pip install wheel && pip wheel . --wheel-dir=/build/wheels

FROM python:3.13-bookworm
COPY --from=builder /build/scripts/* /usr/local/bin/
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/* && rm -rf /tmp/wheels
WORKDIR /root
