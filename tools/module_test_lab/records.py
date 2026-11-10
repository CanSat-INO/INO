"""Local experiment ledger, safe ZIP sharing, and CSV export (stdlib only)."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile

import project_store

DATA_DIR = project_store.data_dir()
RECORDS_FILE = DATA_DIR / "records.json"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
FORMAT = "cansat-module-lab-records"
FORMAT_VERSION = 1
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def setup_data():
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if not RECORDS_FILE.exists():
        save_records([])


def load_records() -> list[dict]:
    setup_data()
    data = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT or data.get("version") != FORMAT_VERSION:
        raise ValueError("Unsupported local record format")
    return data["records"]


def save_records(records: list[dict]):
    records = [project_store.validate_record_project(record) for record in records]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"format": FORMAT, "version": FORMAT_VERSION, "records": records}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, name = tempfile.mkstemp(dir=DATA_DIR, prefix=".records-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(name, RECORDS_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def new_record(**kwargs) -> dict:
    result = {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "module": "着地検知",
        "tester": "",
        "mode": "仮想参考モデル",
        "scenario": "",
        "code_version": "",
        "status": "未判定",
        "expected": "",
        "observed": "",
        "notes": "",
        "metrics": {},
        "attachments": [],
    }
    result.update(kwargs)
    if project_store.active_id():
        result["project_id"] = project_store.active_id()
    return result


def add_record(record: dict, attachment_sources: list[Path] | None = None) -> dict:
    record = project_store.validate_record_project(record)
    existing = load_records()
    if any(r["id"] == record["id"] for r in existing):
        raise ValueError("Duplicate ID")
    for src in attachment_sources or []:
        src = Path(src)
        if not src.is_file() or src.stat().st_size > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"Attachment not found or >10 MB: {src}")
        # Names are stored under a generated ID directory, never user-controlled paths.
        safe_name = src.name
        target = ATTACHMENTS_DIR / record["id"] / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        record["attachments"].append({
            "name": safe_name,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
        })
    existing.append(record)
    save_records(existing)
    return record


def store_trace(record: dict, trace: list[dict]):
    project_store.validate_record_project(record)
    ATTACHMENTS_DIR.joinpath(record["id"]).mkdir(parents=True, exist_ok=True)
    dest = ATTACHMENTS_DIR / record["id"] / "virtual_sensor_trace.csv"
    with dest.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time_s", "imu_z_mps2", "pressure_pa", "truth_contact"])
        w.writeheader()
        w.writerows(trace)
    record["attachments"].append({"name": dest.name,
        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "bytes": dest.stat().st_size})


def export_bundle(record_ids: list[str], destination: Path) -> int:
    records = [r for r in load_records() if r["id"] in set(record_ids)]
    if not records:
        raise ValueError("No records selected")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("records.json", json.dumps({"format": FORMAT,
                    "version": FORMAT_VERSION, "records": records}, ensure_ascii=False, indent=2))
        for r in records:
            for a in r.get("attachments", []):
                src = ATTACHMENTS_DIR / r["id"] / a["name"]
                if src.is_file():
                    z.write(src, f"attachments/{r['id']}/{a['name']}")
    return len(records)


def import_bundle(bundle_path: Path) -> dict:
    existing = load_records()
    known = {r["id"]: r for r in existing}
    added = 0
    skipped = 0
    conflicts = 0
    with zipfile.ZipFile(bundle_path) as z:
        if "records.json" not in z.namelist() or z.getinfo("records.json").file_size > 2_000_000:
            raise ValueError("Invalid experiment ZIP (records.json missing or too large)")
        obj = json.loads(z.read("records.json"))
        if obj.get("format") != FORMAT or obj.get("version") != FORMAT_VERSION:
            raise ValueError("Unsupported ZIP record format")
        records = obj.get("records", [])
        if not isinstance(records, list) or len(records) > 1000:
            raise ValueError("Too many records")
        staged = []
        for rec in records:
            rec = project_store.validate_record_project(rec, allow_unclassified=True)
            rid = rec.get("id")
            if not isinstance(rid, str) or len(rid) != 32 or not all(c in "0123456789abcdef" for c in rid):
                raise ValueError("Invalid record ID")
            if rid in known:
                if known[rid] == rec:
                    skipped += 1
                else:
                    conflicts += 1
                continue
            items = rec.get("attachments", [])
            if not isinstance(items, list) or len(items) > 20:
                raise ValueError("Too many attachments")
            content = []
            for a in items:
                name = a.get("name")
                if (not isinstance(name, str) or name in ("", ".", "..") or
                    Path(name).name != name or "/" in name or "\\" in name):
                    raise ValueError("Invalid attachment filename")
                zip_name = f"attachments/{rid}/{name}"
                if zip_name not in z.namelist():
                    raise ValueError(f"Missing attachment: {name}")
                info = z.getinfo(zip_name)
                if info.file_size > MAX_ATTACHMENT_BYTES:
                    raise ValueError("Attachment too large")
                raw = z.read(zip_name)
                if hashlib.sha256(raw).hexdigest() != a.get("sha256"):
                    raise ValueError("Attachment checksum mismatch")
                content.append((name, raw))
            staged.append((rec, content))
            known[rid] = rec
        # All validation completed before modifying the ledger.
        for rec, content in staged:
            directory = ATTACHMENTS_DIR / rec["id"]
            directory.mkdir(parents=True, exist_ok=True)
            for name, raw in content:
                (directory / name).write_bytes(raw)
            existing.append(rec)
            added += 1
        if staged:
            save_records(existing)
    return {"added": added, "skipped": skipped, "conflicts": conflicts}


def export_csv(destination: Path) -> int:
    records = load_records()
    fields = ["id", "created_at", "module", "tester", "mode", "scenario", "code_version",
              "status", "expected", "observed", "notes", "delay_s", "detected_time_s", "attachment_names"]
    with Path(destination).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            row = {k: r.get(k, "") for k in fields}
            row["delay_s"] = r.get("metrics", {}).get("delay_s", "")
            row["detected_time_s"] = r.get("metrics", {}).get("detected_time_s", "")
            row["attachment_names"] = "; ".join(a.get("name", "") for a in r.get("attachments", []))
            writer.writerow(row)
    return len(records)
