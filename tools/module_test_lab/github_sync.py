"""Opt-in GitHub synchronization for CanSat Module Test Lab.

Each experiment is stored separately as a JSON manifest in a GitHub repository.
Attachments are uploaded first, then the manifest; receivers only see complete
experiments. Uses the authenticated GitHub CLI (gh), never handles auth tokens.
Does not modify the local Git checkout, branches, or program source files.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote
import zipfile
import uuid
from datetime import datetime, timezone

import records
from record_trash import deleted_ids

REPO_DEFAULT = "CanSat-INO/INO"
BRANCH_DEFAULT = "main"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
# New storage layout for INO. Legacy data remains readable, never relocated/deleted.
REMOTE_RECORDS = "data/ino/records"
REMOTE_ATTACHMENTS = "data/ino/attachments"
LEGACY_REMOTE_RECORDS = "experiments/records"
LEGACY_REMOTE_ATTACHMENTS = "experiments/attachments"
MAX_SYNC_ATTACHMENT_BYTES = 900 * 1024
MAX_REMOTE_MANIFEST_BYTES = 300_000


class SyncError(Exception):
    """Safe UI-visible synchronization failure."""


def _check_record_id(record_id: str) -> None:
    if not isinstance(record_id, str) or ID_RE.fullmatch(record_id) is None:
        raise SyncError("不正な実験IDです。")


def _check_filename(name: str) -> None:
    if (not isinstance(name, str) or not name or name in (".", "..")
        or len(name) > 200 or PurePosixPath(name).name != name
        or "/" in name or "\\" in name):
        raise SyncError("添付ファイルの名前が不正です。")


class GitHubSync:
    def __init__(self, repository: str = REPO_DEFAULT, branch: str = BRANCH_DEFAULT):
        if not REPO_RE.fullmatch(repository):
            raise SyncError("リポジトリは owner/repository 形式で指定してください。")
        if (not REF_RE.fullmatch(branch) or ".." in branch or branch.startswith("/")
            or branch.endswith("/") or "//" in branch):
            raise SyncError("ブランチ名が不正です。")
        self.repo = repository
        self.branch = branch

    def _api(self, method: str, endpoint: str, data: dict | None = None, *, allow_404=False):
        cmd = ["gh", "api", "--method", method.upper(),
               "-H", "Accept: application/vnd.github+json", endpoint]
        if data is not None:
            cmd.extend(["--input", "-"])
        try:
            proc = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                                  text=True, capture_output=True, timeout=90, check=False)
        except FileNotFoundError as exc:
            raise SyncError("GitHub CLI (gh) が見つかりません。sudo apt install gh を実行してください。") from exc
        except subprocess.TimeoutExpired as exc:
            raise SyncError("GitHubへの接続がタイムアウトしました。通信を確認してください。") from exc
        if proc.returncode:
            error = proc.stderr.strip()
            if allow_404 and ("HTTP 404" in error or "Not Found (HTTP 404)" in error):
                return None
            # Never echo full CLI output: it can contain server echoes of user data.
            if "HTTP 403" in error or "HTTP 401" in error:
                raise SyncError("GitHubへのアクセス権がありません。gh auth status とリポジトリの権限を確認してください。")
            if "HTTP 404" in error:
                raise SyncError("リポジトリまたはブランチが見つかりません。gh auth status を確認してください。")
            if "HTTP 409" in error or "HTTP 422" in error:
                raise SyncError("GitHubの更新が競合しました。同期をやり直してください。")
            raise SyncError(f"GitHub APIへの接続に失敗しました（終了コード {proc.returncode}）。")
        if not proc.stdout.strip():
            return {}
        try:
            return json.loads(proc.stdout)
        except ValueError as exc:
            raise SyncError("GitHub APIから想定外の応答が返されました。") from exc

    def _contents_url(self, path: str, *, ref: bool = False) -> str:
        path = "/".join(quote(p, safe="") for p in PurePosixPath(path).parts)
        endpoint = f"repos/{self.repo}/contents/{path}"
        if ref:
            endpoint += f"?ref={quote(self.branch, safe='')}"
        return endpoint

    def check_access(self) -> str:
        data = self._api("GET", f"repos/{self.repo}")
        default = data.get("default_branch", "不明")
        visibility = ("非公開" if data.get("private") is True else
                      "公開" if data.get("private") is False else "未確認")
        self._api("GET", f"repos/{self.repo}/branches/{quote(self.branch, safe='')}")
        return (f"{data.get('full_name', self.repo)} / {self.branch}"
                f"（デフォルト: {default}、公開状態: {visibility}）")

    def _require_private_repository(self) -> None:
        """Do not accidentally publish lab records to a public repository."""
        data = self._api("GET", f"repos/{self.repo}")
        if data.get("private") is not True:
            raise SyncError("リポジトリの非公開状態を確認できません。実験データの送信を中止しました。")

    @staticmethod
    def _backup_before_download() -> Path:
        """Copy the entire local ledger before the first remote import."""
        records.setup_data()
        backup_root = records.DATA_DIR.parent / (records.DATA_DIR.name + "_backups")
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backup_root / f"before_github_download_{stamp}_{uuid.uuid4().hex[:8]}"
        try:
            shutil.copytree(records.DATA_DIR, dest, symlinks=True)
        except OSError as exc:
            raise SyncError("ローカルデータのバックアップに失敗したため、取得を中止しました。") from exc
        return dest

    def _get_file(self, path: str) -> bytes | None:
        response = self._api("GET", self._contents_url(path, ref=True), allow_404=True)
        if response is None:
            return None
        if response.get("type") != "file":
            raise SyncError("GitHubの保存先にファイル以外の項目があります。")
        encoded = response.get("content")
        if response.get("encoding") != "base64" or not isinstance(encoded, str):
            raise SyncError("GitHubからファイル内容を取得できません。")
        try:
            return base64.b64decode(encoded, validate=False)
        except Exception as exc:
            raise SyncError("GitHub上のファイルを読み取れません。") from exc

    def _put_new_file(self, path: str, raw: bytes, description: str) -> bool:
        existing = self._get_file(path)
        if existing is not None:
            if existing == raw:
                return False
            raise SyncError(f"GitHub上に同名で内容が異なるファイルがあります（上書きしません）: {path}")
        self._api("PUT", self._contents_url(path), {
            "message": description,
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": self.branch,
        })
        return True

    @staticmethod
    def _record_payload(rec: dict) -> bytes:
        return (json.dumps({"format": records.FORMAT,
                            "version": records.FORMAT_VERSION,
                            "records": [rec]}, ensure_ascii=False,
                           indent=2, sort_keys=True) + "\n").encode("utf-8")

    def upload(self, record_ids: list[str]) -> dict:
        """Upload selected local records. Safe to retry; refuses conflicting IDs."""
        if not record_ids:
            raise SyncError("アップロードする実験結果を選択してください。")
        self._require_private_repository()
        local = {r["id"]: r for r in records.load_records()}
        sent = skipped = 0
        for rid in dict.fromkeys(record_ids):
            _check_record_id(rid)
            if rid not in local:
                raise SyncError(f"ローカルに実験記録 {rid} がありません。")
            rec = local[rid]
            manifest = self._record_payload(rec)
            if len(manifest) > MAX_REMOTE_MANIFEST_BYTES:
                raise SyncError("実験記録が大きすぎます。メモやログを分割してください。")
            manifest_path = f"{REMOTE_RECORDS}/{rid}.json"
            # Refuse ID collisions across both the old and new layouts.
            # Identical legacy records remain at their old path; never duplicate them.
            existing_anywhere = False
            for root in (REMOTE_RECORDS, LEGACY_REMOTE_RECORDS):
                previous = self._get_file(f"{root}/{rid}.json")
                if previous is not None:
                    if previous != manifest:
                        raise SyncError(
                            f"ID {rid[:12]} の記録がGitHub上に既に存在し、内容が異なります。"
                            "新旧いずれの保存先も上書きしません。")
                    existing_anywhere = True
            if existing_anywhere:
                skipped += 1
                continue
            # Write attachments BEFORE manifest so partially finished pushes
            # are not visible as an incomplete experiment to other users.
            for attachment in rec.get("attachments", []):
                name = attachment.get("name")
                _check_filename(name)
                local_path = records.ATTACHMENTS_DIR / rid / name
                if not local_path.is_file():
                    raise SyncError(f"添付ファイルがありません: {local_path}")
                if local_path.stat().st_size > MAX_SYNC_ATTACHMENT_BYTES:
                    raise SyncError(f"GitHub同期は添付1個あたり900KB以下です: {name}")
                content = local_path.read_bytes()
                if hashlib.sha256(content).hexdigest() != attachment.get("sha256"):
                    raise SyncError(f"添付ファイルが記録時から変更されています: {name}")
                self._put_new_file(f"{REMOTE_ATTACHMENTS}/{rid}/{name}", content,
                                   f"experiments: attach {rid[:12]} {name}")
            self._put_new_file(manifest_path, manifest, f"experiments: add {rid[:12]}")
            sent += 1
        return {"uploaded": sent, "skipped": skipped}

    def download(self) -> dict:
        """Read both INO and legacy GitHub locations, merging without overwrites.

        New data/ino records take precedence when the same manifest exists in both.
        A divergent manifest with the same ID across locations is an error: never
        silently select one, overwrite local data, or delete anything remotely.
        """
        # Record-ID -> [(remote records root, remote attachments root), ...].
        # Preserve priority: the new INO path is checked before the legacy path.
        locations: dict[str, list[tuple[str, str]]] = {}
        for record_root, attach_root in (
            (REMOTE_RECORDS, REMOTE_ATTACHMENTS),
            (LEGACY_REMOTE_RECORDS, LEGACY_REMOTE_ATTACHMENTS),
        ):
            listing = self._api("GET", self._contents_url(record_root, ref=True), allow_404=True)
            if listing is None:
                continue
            if not isinstance(listing, list):
                raise SyncError(f"GitHubの実験記録フォルダの形式が想定外です: {record_root}")
            if len(listing) >= 1000:
                raise SyncError("GitHub Contents APIの一覧上限に達しました。管理方式の拡張が必要です。")
            for entry in listing:
                if not isinstance(entry, dict):
                    raise SyncError("GitHubの実験記録一覧が不正です。")
                filename = entry.get("name", "")
                if (not isinstance(filename, str) or not filename.endswith(".json")
                    or ID_RE.fullmatch(filename[:-5]) is None):
                    continue
                rid = filename[:-5]
                locations.setdefault(rid, []).append((record_root, attach_root))

        if not locations:
            return {"added": 0, "skipped": 0, "conflicts": 0, "remote": 0}
        local = {r["id"]: r for r in records.load_records()}
        added = skipped = conflicts = skipped_deleted = 0
        local_deleted = deleted_ids()
        backup = None
        for rid in sorted(locations):
            if rid in local_deleted and rid not in local:
                skipped_deleted += 1
                continue
            record_root, attach_root = locations[rid][0]
            raw = self._get_file(f"{record_root}/{rid}.json")
            if raw is None or len(raw) > MAX_REMOTE_MANIFEST_BYTES:
                raise SyncError(f"GitHubの実験記録 {rid[:12]} が破損・過大です。")
            # Compare both locations when an ID is present twice. This also
            # prevents hiding an old conflicting experiment under the new path.
            for alternate_root, _ in locations[rid][1:]:
                alternate = self._get_file(f"{alternate_root}/{rid}.json")
                if alternate is None or alternate != raw:
                    raise SyncError(
                        f"GitHubの新旧保存先にID {rid[:12]} の異なる記録があります。"
                        "安全のため取り込みません。")
            try:
                obj = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise SyncError(f"GitHubの実験記録 {rid[:12]} が不正です。") from exc
            remote_records = obj.get("records") if isinstance(obj, dict) else None
            if (not isinstance(obj, dict) or
                obj.get("format") != records.FORMAT or
                obj.get("version") != records.FORMAT_VERSION or
                not isinstance(remote_records, list) or len(remote_records) != 1 or
                not isinstance(remote_records[0], dict) or remote_records[0].get("id") != rid):
                raise SyncError(f"GitHubの実験記録 {rid[:12]} の形式が一致しません。")
            rec = remote_records[0]
            if rid in local:
                if rec == local[rid]:
                    skipped += 1
                else:
                    conflicts += 1
                continue
            attachments = rec.get("attachments", [])
            if not isinstance(attachments, list) or len(attachments) > 20:
                raise SyncError("添付情報が不正です。")
            with tempfile.TemporaryDirectory(prefix="cansat-sync-") as t:
                bundle = Path(t) / "received.zip"
                with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("records.json", json.dumps({"format": records.FORMAT,
                        "version": records.FORMAT_VERSION, "records": [rec]}, ensure_ascii=False))
                    for attach in attachments:
                        name = attach.get("name") if isinstance(attach, dict) else None
                        _check_filename(name)
                        raw_attach = self._get_file(f"{attach_root}/{rid}/{name}")
                        if raw_attach is None or len(raw_attach) > MAX_SYNC_ATTACHMENT_BYTES:
                            raise SyncError(f"実験 {rid[:12]} の添付ファイルが欠損・過大です: {name}")
                        if hashlib.sha256(raw_attach).hexdigest() != attach.get("sha256"):
                            raise SyncError(f"GitHub上の添付ファイルのSHA256が一致しません: {name}")
                        # Never overwrite an orphan from an interrupted import.
                        target = records.ATTACHMENTS_DIR / rid / name
                        if target.parent.is_symlink() or target.exists() or target.is_symlink():
                            raise SyncError(
                                f"既存のローカル添付ファイルを保護するため取得を中止しました: {rid[:12]}/{name}")
                        z.writestr(f"attachments/{rid}/{name}", raw_attach)
                if backup is None:
                    backup = self._backup_before_download()
                result = records.import_bundle(bundle)
                added += result["added"]
                skipped += result["skipped"]
                conflicts += result["conflicts"]
                if result["added"]:
                    local[rid] = rec
        return {"added": added, "skipped": skipped, "conflicts": conflicts,
                "remote": len(locations), "skipped_deleted": skipped_deleted,
                "backup": str(backup) if backup else None}
