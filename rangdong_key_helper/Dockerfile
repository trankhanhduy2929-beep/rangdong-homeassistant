FROM python:3.13.15-slim-trixie

ARG BUILD_ARCH
ARG BUILD_VERSION

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="Rạng Đông Key Helper" \
    org.opencontainers.image.description="Rooted Android ADB and Frida helper for Rạng Đông Smart" \
    org.opencontainers.image.source="https://github.com/trankhanhduy2929-beep/rangdong-homeassistant" \
    org.opencontainers.image.licenses="MIT AND (LGPL-2.0-or-later WITH WxWindows-exception-3.1)"

ENV HOME=/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes adb ca-certificates \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt

COPY LICENSE THIRD_PARTY_NOTICES.md LICENSE.frida.txt /usr/share/doc/rangdong-key-helper/
COPY rootfs/app /app
WORKDIR /app

EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3).read()"]
CMD ["python3", "-m", "rangdong_helper"]
