"""Import shipped renderer artifacts without executing the application."""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=Path("/Applications/AiCoin.app"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "reference/aicoin")
    args = parser.parse_args()
    archive = args.app / "Contents/Resources/app.asar"
    if args.output.exists():
        raise SystemExit("Output already exists; select a new directory to preserve previous evidence")
    records = []
    with archive.open("rb") as source:
        prefix = source.read(16)
        _, header_size, _, json_size = struct.unpack("<4I", prefix)
        if not 0 < json_size < header_size < 16 * 1024 * 1024:
            raise ValueError("Invalid ASAR header")
        header = json.loads(source.read(json_size))
        data_start = 8 + header_size

        def read(entry):
            if entry.get("unpacked") or "link" in entry:
                raise ValueError("Renderer must contain ordinary packed files")
            source.seek(data_start + int(entry["offset"]))
            data = source.read(entry["size"])
            if len(data) != entry["size"]:
                raise ValueError("Truncated ASAR member")
            expected = entry.get("integrity", {})
            digest = hashlib.sha256(data).hexdigest()
            if expected and (expected.get("algorithm") != "SHA256" or expected.get("hash") != digest):
                raise ValueError("ASAR member integrity mismatch")
            return data, digest, bool(expected)

        package, _, _ = read(header["files"]["package.json"])
        version = json.loads(package)["version"]

        def walk(tree, relative=PurePosixPath()):
            for name, entry in tree["files"].items():
                if name in (".", "..") or "/" in name or "\\" in name:
                    raise ValueError("Invalid member name")
                target = relative / name
                if "files" in entry:
                    walk(entry, target)
                else:
                    data, digest, verified = read(entry)
                    output = args.output / "renderer" / str(target)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(data)
                    records.append({"path": str(target), "size": len(data), "sha256": digest, "declared_integrity_verified": verified})

        walk(header["files"]["dist"]["files"]["renderer"])
    counts = dict(Counter(Path(row["path"]).suffix for row in records))
    with archive.open("rb") as source:
        archive_digest = hashlib.file_digest(source, "sha256").hexdigest()
    manifest = {"app_version": version, "archive_sha256": archive_digest,
                "scope": "dist/renderer only; no application execution, native code, user profile or credentials",
                "source_form": "shipped bundles; original source unavailable unless explicitly included",
                "counts": counts, "file_count": len(records), "total_bytes": sum(row["size"] for row in records), "files": records}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("app_version", "file_count", "total_bytes", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
