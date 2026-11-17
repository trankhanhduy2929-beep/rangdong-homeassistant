"""Create ZIP distributions without secrets, caches or proprietary test inputs."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist"


def safe(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    excluded = {
        "node_modules",
        ".git",
        ".next",
        ".vercel",
        ".wrangler",
        "dist",
        "target",
        "private",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
    if any(part in excluded for part in relative.parts) or path.is_symlink():
        return False
    name = path.name
    return not (
        (name.startswith(".env") and name != ".env.example")
        or name.startswith(".dev.vars")
        or path.suffix
        in {".apk", ".so", ".zip", ".pyc", ".token", ".pem", ".tsbuildinfo"}
        or name in {"classpath.txt", "app-credentials", "server-secrets.env"}
    )


def archive(
    name: str, paths: list[Path], prefix: Path = ROOT, local_addon: bool = False
) -> Path:
    output = OUTPUT / name
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for path in sorted(paths):
            if not safe(path):
                continue
            relative = path.relative_to(prefix).as_posix()
            if local_addon and relative == "rangdong_key_helper/config.yaml":
                content = (
                    "\n".join(
                        line
                        for line in path.read_text().splitlines()
                        if not line.startswith("image:")
                    )
                    + "\n"
                )
                target.writestr(relative, content)
            else:
                target.write(path, relative)
    with zipfile.ZipFile(output) as target:
        if target.testzip():
            raise RuntimeError("Archive integrity failure")
    return output


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    version = json.loads(
        (ROOT / "custom_components/rangdong_smart/manifest.json").read_text()
    )["version"]
    config = ast.parse(
        (ROOT / "custom_components/rangdong_smart/license_config.py").read_text()
    )
    settings = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in config.body
        if isinstance(node, ast.Assign)
    }
    mode = "licensed" if settings["ENFORCE"] else "setup"
    if settings["ENFORCE"] and (
        not settings["SERVER_URL"] or not settings["VERIFY_PUBLIC_KEY"]
    ):
        raise RuntimeError("Configure licensing first")
    if (ROOT / ".git").exists():
        listed = (
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                cwd=ROOT,
            )
            .decode()
            .split("\0")
        )
        files = [
            ROOT / name for name in set(listed) if name and (ROOT / name).is_file()
        ]
    else:
        files = []
        roots = {
            "custom_components",
            "rangdong_key_helper",
            "license-server",
            "tools",
            "tests",
            ".github",
            "poc",
        }
        root_files = {
            "README.md",
            "LICENSE",
            "LICENSE_DEPLOY_VI.md",
            "REPORT_LICENSE.md",
            "DEPLOY_STATUS_VI.md",
            "hacs.json",
            "repository.yaml",
            ".gitignore",
            ".ruff.toml",
        }
        for directory, children, names in os.walk(ROOT):
            parent = Path(directory)
            children[:] = [
                name
                for name in children
                if safe(parent / name) and (parent != ROOT or name in roots)
            ]
            files.extend(
                parent / name for name in names if parent != ROOT or name in root_files
            )
    artifacts = [
        archive(
            f"rangdong_smart-v{version}-{mode}.zip",
            [
                path
                for path in files
                if path.is_relative_to(ROOT / "custom_components/rangdong_smart")
            ],
        ),
        archive(
            f"rangdong-key-helper-local-{version}-{mode}.zip",
            [
                path
                for path in files
                if path.is_relative_to(ROOT / "rangdong_key_helper")
            ],
            local_addon=True,
        ),
        archive(
            "rangdong-license-server-1.0.0.zip",
            [path for path in files if path.is_relative_to(ROOT / "license-server")],
            ROOT / "license-server",
        ),
        archive(f"rangdong-source-{version}-{mode}.zip", files),
    ]
    expected = [
        f"rangdong_smart-v{version}-licensed.zip",
        f"rangdong_smart-v{version}-setup.zip",
        f"rangdong-key-helper-local-{version}-licensed.zip",
        f"rangdong-key-helper-local-{version}-setup.zip",
        f"rangdong-source-{version}-licensed.zip",
        f"rangdong-source-{version}-setup.zip",
        "rangdong-license-server-1.0.0.zip",
    ]
    checksums = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for name in expected
        if (path := OUTPUT / name).is_file()
    ]
    (OUTPUT / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n")
    for path in artifacts:
        print(f"{path.name}: {path.stat().st_size} bytes")
    print(f"Mode: {mode}. No GitHub push performed.")


if __name__ == "__main__":
    main()
