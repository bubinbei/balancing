"""Detect stale non-editable wheels before accepting release checks."""

import argparse
import hashlib
import json
from pathlib import Path

import balancing_host


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sources = args.root.resolve() / "host" / "balancing_host"
    installed = Path(balancing_host.__file__).resolve().parent
    if installed == sources:
        print("Use a non-editable verification environment, not the working editable package.")
        return 1
    mismatches = []
    digest = hashlib.sha256()
    files = sorted(sources.glob("*.py"))
    for source in files:
        data = source.read_bytes()
        digest.update(source.name.encode("ascii") + b"\0" + data)
        target = installed / source.name
        if not target.is_file() or target.read_bytes() != data:
            mismatches.append(source.name)
    extras = {p.name for p in installed.glob("*.py")} - {p.name for p in files}
    mismatches += sorted(extras)
    assets = sorted((sources / "demo_assets").glob("*"))
    asset_digest = hashlib.sha256()
    for source in assets:
        data = source.read_bytes()
        asset_digest.update(source.name.encode("ascii") + b"\0" + data)
        target = installed / "demo_assets" / source.name
        if not target.is_file() or target.read_bytes() != data:
            mismatches.append("demo_assets/" + source.name)
    asset_extras = {p.name for p in (installed / "demo_assets").glob("*")} - {p.name for p in assets}
    mismatches += sorted("demo_assets/" + name for name in asset_extras)
    result = dict(ok=not mismatches, checked_files=len(files), mismatches=mismatches,
                  host_source_sha256=digest.hexdigest(), checked_assets=len(assets),
                  demo_assets_sha256=asset_digest.hexdigest())
    print(json.dumps(result, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
