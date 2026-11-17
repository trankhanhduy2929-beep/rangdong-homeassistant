"""Set public licensing settings before building customer distributions."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from urllib.parse import urlparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--public-key-file", type=Path, required=True)
    parser.add_argument("--compatibility", action="store_true")
    args = parser.parse_args()
    url = urlparse(args.server)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error(
            "Server must be an HTTPS origin without credentials, path or query"
        )
    public = args.public_key_file.read_text().strip()
    if len(base64.b64decode(public, validate=True)) != 32:
        parser.error("Expected a 32-byte Ed25519 public key in Base64")
    root = Path(__file__).resolve().parents[1]
    origin = f"https://{url.netloc}"
    common = (
        f"SERVER_URL = {json.dumps(origin)}\nENFORCE = {not args.compatibility!r}\n"
    )
    (root / "custom_components/rangdong_smart/license_config.py").write_text(
        '"""Public license deployment configuration."""\n\n'
        + common
        + f"VERIFY_PUBLIC_KEY = {json.dumps(public)}\n"
    )
    (
        root / "rangdong_key_helper/rootfs/app/rangdong_helper/license_config.py"
    ).write_text('"""Public license deployment configuration."""\n\n' + common)
    print("Configured public origin and verification key for both components.")
    print(
        "Compatibility mode"
        if args.compatibility
        else "License enforcement enabled for new setup and key collection."
    )


if __name__ == "__main__":
    main()
