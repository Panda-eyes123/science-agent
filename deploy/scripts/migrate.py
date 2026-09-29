"""Copy legacy host data into Docker volumes, verify it, and rebase provenance.

Run with the API stopped and the old host directory mounted read-only at /legacy.
Files are never overwritten with different content. Milvus rows are backed up
before modifying only the configured corpus's file references.
"""
import argparse
import hashlib
import json
import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def copy_verified(source: Path, target: Path) -> list[dict]:
    if not source.exists():
        return []
    rows = []
    root = source.resolve()
    for path in sorted(source.rglob("*")):
        if path.is_symlink() and path.is_dir():
            raise ValueError(f"Directory links require manual migration: {path}")
        if not path.is_file():
            continue
        # HF snapshots may use links, but they must stay within this cache.
        path.resolve().relative_to(root)
        relative = path.relative_to(source)
        destination = target / relative
        destination.resolve().relative_to(target.resolve())
        checksum = digest(path)
        if destination.exists() and digest(destination) != checksum:
            raise ValueError(f"Refusing to overwrite different data: {destination}")
        rows.append({"path": str(relative), "sha256": checksum})
    for row in rows:
        destination = target / row["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source / row["path"], destination)
        if digest(destination) != row["sha256"]:
            raise ValueError(f"Copy verification failed: {destination}")
    return rows


def rebase_path(value: str, old_root: str, new_root: Path) -> str:
    normalized = value.replace("\\", "/")
    prefix = old_root.replace("\\", "/").rstrip("/") + "/"
    if not normalized.lower().startswith(prefix.lower()):
        return value
    relative = PurePosixPath(normalized[len(prefix):])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid stored path: {value}")
    destination = new_root.joinpath(*relative.parts)
    destination.resolve().relative_to(new_root.resolve())
    if not destination.is_file():
        raise FileNotFoundError(destination)
    return str(destination)


def rebase_corpus(old_root: str, data: Path, backup: Path) -> int:
    from pymilvus import MilvusClient

    collection = os.getenv("MILVUS_COLLECTION", "science_web_papers") + "_records"
    client = MilvusClient(uri=os.getenv("MILVUS_URI", "http://milvus:19530"))
    changed = 0
    try:
        if not client.has_collection(collection):
            return 0
        iterator = client.query_iterator(
            collection_name=collection,
            filter='record_type in ["paper", "element"]',
            output_fields=["record_id", "record_type", "payload", "record_vector"],
            batch_size=100,
            consistency_level="Strong",
        )
        updates = []
        try:
            with (backup / "milvus-records.jsonl").open("x", encoding="utf-8") as saved:
                while rows := iterator.next():
                    for row in rows:
                        payload = row["payload"].copy()
                        field = "source_path" if row["record_type"] == "paper" else "image_path"
                        original = payload.get(field)
                        if not original:
                            continue
                        rebased = rebase_path(original, old_root, data)
                        if original == rebased:
                            continue
                        saved.write(json.dumps(row, ensure_ascii=False) + "\n")
                        payload[field] = rebased
                        updates.append({**row, "payload": payload})
                saved.flush()
                os.fsync(saved.fileno())
        finally:
            iterator.close()
        for start in range(0, len(updates), 100):
            batch = updates[start:start + 100]
            client.upsert(collection_name=collection, data=batch)
            checked = client.get(
                collection_name=collection,
                ids=[row["record_id"] for row in batch],
                output_fields=["payload"],
                consistency_level="Strong",
            )
            expected = {row["record_id"]: row["payload"] for row in batch}
            if {row["record_id"]: row["payload"] for row in checked} != expected:
                raise RuntimeError("Milvus provenance verification failed")
            changed += len(batch)
        return changed
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", type=Path, default=Path("/legacy"))
    parser.add_argument("--data-subdir", default="data")
    parser.add_argument("--old-data-root", required=True)
    parser.add_argument("--skip-milvus", action="store_true")
    args = parser.parse_args()
    legacy = args.legacy.resolve(strict=True)
    source = (legacy / args.data_subdir).resolve(strict=True)
    source.relative_to(legacy)
    data, cache = Path("/data"), Path("/cache")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = Path("/backups") / stamp
    backup.mkdir(parents=True, exist_ok=False)
    with tarfile.open(backup / "legacy-data.tar.gz", "w:gz") as archive:
        archive.add(source, arcname="data")
        if (legacy / "workspaces").exists():
            archive.add(legacy / "workspaces", arcname="sdk-workspaces")
    manifest = {
        "data": copy_verified(source, data),
        "sdk_workspaces": copy_verified(legacy / "workspaces", data / "workspaces"),
        "huggingface": copy_verified(legacy / "cache/huggingface", cache / "huggingface"),
        "docling": copy_verified(legacy / "cache/docling", cache / "docling"),
    }
    if not args.skip_milvus:
        manifest["rebased_records"] = rebase_corpus(args.old_data_root, data, backup)
    for root in (data, cache):
        os.chown(root, 10001, 10001)
        for path in root.rglob("*"):
            os.chown(path, 10001, 10001)
    (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "backup": str(backup),
        "verified_files": sum(len(rows) for rows in manifest.values() if isinstance(rows, list)),
        "rebased_records": manifest.get("rebased_records", 0),
    }))


if __name__ == "__main__":
    main()
