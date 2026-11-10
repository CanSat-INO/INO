"""Reversible LOCAL record removal, never changes remote GitHub data.

Selected records and their complete attachment directories are compressed to a
ZIP outside the live data directory before anything in the live ledger changes.
Deleted IDs are recorded locally so GitHub download will not re-import them.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid
import zipfile

import records

ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
TRASH_DIR_NAME = "cansat_module_lab_trash"
TOMBSTONE_FILENAME = "locally_deleted_ids.json"


class TrashError(ValueError):
    """Refuse risky or incompatible file operations."""


def tombstone_file() -> Path:
    return records.DATA_DIR / TOMBSTONE_FILENAME


def deleted_ids() -> set[str]:
    path = tombstone_file()
    if not path.exists():
        return set()
    if path.is_symlink():
        raise TrashError("削除ID台帳がシンボリックリンクです。安全のため中止します。")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("version") != 1 or not isinstance(obj.get("ids"), list):
        raise TrashError("削除ID台帳の形式が不正です。")
    ids = obj["ids"]
    if any(not isinstance(x, str) or not ID_PATTERN.fullmatch(x) for x in ids):
        raise TrashError("削除ID台帳に不正なIDがあります。")
    return set(ids)


def _save_deleted_ids(ids: set[str]) -> None:
    path = tombstone_file()
    if path.is_symlink():
        raise TrashError("削除ID台帳の保存先がシンボリックリンクです。")
    records.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".deleted-", suffix=".tmp", dir=records.DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "ids": sorted(ids)}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _attachment_files(selected_ids: list[str]) -> list[tuple[str, Path]]:
    result = []
    root = records.ATTACHMENTS_DIR
    if root.is_symlink():
        raise TrashError("添付フォルダがシンボリックリンクです。中止します。")
    for rid in selected_ids:
        directory = root / rid
        if directory.is_symlink():
            raise TrashError("添付フォルダにシンボリックリンクがあります。")
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise TrashError("添付先にフォルダ以外の項目があります。")
        for item in directory.rglob("*"):
            if item.is_symlink():
                raise TrashError("添付内にシンボリックリンクがあります。")
            if not (item.is_file() or item.is_dir()):
                raise TrashError("添付内に未対応のファイル形式があります。")
            if item.is_file():
                rel = item.relative_to(root).as_posix()
                result.append(("attachments/" + rel, item))
    return result


def _archive_root(archive_dir: Path | None) -> Path:
    if archive_dir is not None:
        return Path(archive_dir)
    from project_store import active_id, trash_dir
    return trash_dir() if active_id() else records.DATA_DIR.parent / TRASH_DIR_NAME


def delete_selected(record_ids: list[str], archive_dir: Path | None = None) -> dict:
    """Archive and remove *only* the selected local records and their files."""
    ids = list(dict.fromkeys(record_ids))
    if not ids or any(not isinstance(x, str) or not ID_PATTERN.fullmatch(x) for x in ids):
        raise TrashError("削除対象の実験IDが不正または未選択です。")
    current = records.load_records()
    lookup = {r["id"]: r for r in current}
    if len(lookup) != len(current) or any(rid not in lookup for rid in ids):
        raise TrashError("台帳が変更されたかIDが重複しています。再読み込みしてください。")
    old_deleted = deleted_ids()
    files = _attachment_files(ids)
    chosen = [lookup[rid] for rid in ids]
    root = _archive_root(archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise TrashError("バックアップ先がシンボリックリンクです。中止します。")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = root / f"deleted_{stamp}_{uuid.uuid4().hex[:10]}.zip"
    json_bytes = json.dumps({"format": records.FORMAT, "version": records.FORMAT_VERSION,
                             "records": chosen}, ensure_ascii=False, indent=2).encode("utf-8")
    checksum = {}
    try:
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as z:
            z.writestr("records.json", json_bytes)
            for name, source in files:
                checksum[name] = _hash_file(source)
                z.write(source, name)
        with zipfile.ZipFile(archive, "r") as z:
            if z.testzip() is not None or z.read("records.json") != json_bytes:
                raise TrashError("退避ZIPの検証に失敗しました。削除しません。")
            for name, expected in checksum.items():
                if hashlib.sha256(z.read(name)).hexdigest() != expected:
                    raise TrashError("添付の退避を検証できません。削除しません。")
    except Exception:
        # Incomplete archives are never considered valid. Local data stays intact.
        archive.unlink(missing_ok=True)
        raise

    # No live data changes occur before the complete archive has been verified.
    try:
        _save_deleted_ids(old_deleted | set(ids))
        records.save_records([r for r in current if r["id"] not in ids])
    except Exception:
        _save_deleted_ids(old_deleted)
        raise

    # Any interrupted cleanup leaves archived files available for recovery.
    removed_dirs = 0
    for rid in ids:
        target = records.ATTACHMENTS_DIR / rid
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise TrashError("記録は退避済みですが、添付が安全に削除できません。ZIPを保管してください。")
            shutil.rmtree(target)
            removed_dirs += 1
    return {"deleted": len(ids), "archive": str(archive),
            "attachments": len(files), "attachment_folders": removed_dirs}


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def restore_archive(archive: Path) -> dict:
    """Restore only absent records, never overwrite existing local IDs or files."""
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file():
        raise TrashError("復元するZIPが見つかりません。")
    with zipfile.ZipFile(archive, "r") as z:
        names = z.namelist()
        if not names or len(set(names)) != len(names) or z.testzip() is not None:
            raise TrashError("ZIPに破損や重複ファイルがあります。")
        if "records.json" not in names or z.getinfo("records.json").file_size > 10 * 1024 * 1024:
            raise TrashError("退避ZIPにrecords.jsonがありません。")
        obj = json.loads(z.read("records.json"))
        if obj.get("format") != records.FORMAT or obj.get("version") != records.FORMAT_VERSION:
            raise TrashError("未対応の記録形式です。")
        restored = obj.get("records")
        if not isinstance(restored, list) or not restored:
            raise TrashError("ZIPに復元可能な記録がありません。")
        import project_store
        restored = [project_store.validate_record_project(r) for r in restored]
        ids = [r.get("id") for r in restored if isinstance(r, dict)]
        if (len(ids) != len(restored) or len(ids) != len(set(ids)) or
            any(not isinstance(x, str) or not ID_PATTERN.fullmatch(x) for x in ids)):
            raise TrashError("実験IDが不正です。")
        existing = records.load_records()
        current_ids = {r["id"] for r in existing}
        if current_ids.intersection(ids):
            raise TrashError("同じIDの実験記録が既にあります。上書きせず中止します。")
        files = {}
        for name in names:
            if name == "records.json":
                continue
            posix = PurePosixPath(name)
            if (len(posix.parts) < 3 or posix.parts[0] != "attachments" or
                posix.parts[1] not in ids or posix.is_absolute() or
                any(p in ("", ".", "..") for p in posix.parts) or
                posix.as_posix() != name or "\\" in name):
                raise TrashError("ZIP内に不正なファイル名があります。")
            info = z.getinfo(name)
            if info.is_dir() or ((info.external_attr >> 16) & 0o170000) == 0o120000:
                raise TrashError("ZIPに未対応のファイル形式があります。")
            files[name] = info
        # Refuse even orphan attachment directories to avoid overwriting them.
        if records.ATTACHMENTS_DIR.is_symlink() or any(
            (records.ATTACHMENTS_DIR / rid).exists() or
            (records.ATTACHMENTS_DIR / rid).is_symlink() for rid in ids):
            raise TrashError("同名の添付フォルダがあります。上書きせず中止します。")

        # Extract to a temporary staging directory first and validate each path.
        with tempfile.TemporaryDirectory(prefix="cansat-restore-") as d:
            staging = Path(d)
            for name in files:
                target = staging.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(name) as reader, target.open("xb") as writer:
                    shutil.copyfileobj(reader, writer)
            created_dirs = []
            old_tombstones = deleted_ids()
            try:
                records.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
                for rid in ids:
                    source = staging / "attachments" / rid
                    if source.is_dir():
                        target = records.ATTACHMENTS_DIR / rid
                        shutil.move(str(source), str(target))
                        created_dirs.append(target)
                # JSON save is atomic, so no half-written ledger is exposed.
                records.save_records(existing + restored)
                _save_deleted_ids(old_tombstones - set(ids))
            except Exception:
                # If ledger has already changed, leave recovered data in place;
                # removing the new directories in that situation loses recovery.
                if {r["id"] for r in records.load_records()}.isdisjoint(ids):
                    for folder in created_dirs:
                        if folder.is_dir() and not folder.is_symlink():
                            shutil.rmtree(folder)
                raise
    return {"restored": len(ids), "archive": str(archive)}
