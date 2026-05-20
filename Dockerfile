FROM python:3.13-bookworm AS builder

RUN mkdir /build
COPY . /build
WORKDIR /build

RUN pip install --no-cache-dir wheel==0.47.0 && pip wheel --no-cache-dir . --wheel-dir=/build/wheels

FROM python:3.13-bookworm
COPY --from=builder /build/scripts/* /usr/local/bin/
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/* && rm -rf /tmp/wheels
RUN useradd --create-home --shell /usr/sbin/nologin borme
WORKDIR /home/borme
USER borme
