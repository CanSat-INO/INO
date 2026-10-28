from __future__ import annotations
from pathlib import Path
import hashlib
import importlib.util
import pytest

ROOT = Path(__file__).resolve().parents[4]
INSTALLER = ROOT / 'install_v19.py'


def get_module():
    spec = importlib.util.spec_from_file_location('v19_installer_for_test', INSTALLER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_repository(tmp_path, installer):
    repo=tmp_path/'INO-module-lab'
    target=repo/'tools/module_test_lab'; target.mkdir(parents=True)
    src=ROOT/'test_fixtures/v18_app.py'
    # Fixture is reconstructed from the package dependency's original v18 app.
    assert src.is_file()
    (target/'app.py').write_bytes(src.read_bytes())
    for name in installer.PREREQUISITES:
        if name!='app.py':
            (target/name).write_text('fixture',encoding='utf-8')
    return repo,target


def test_install_dryrun_reapply_and_backup(tmp_path):
    ins=get_module()
    repo,target=fake_repository(tmp_path,ins)
    previous=(target/'app.py').read_bytes()
    assert ins.install(repo,dry_run=True,backup_root=tmp_path/'backups') is None
    assert (target/'app.py').read_bytes()==previous
    result=ins.install(repo,backup_root=tmp_path/'backups')
    assert result.is_dir()
    assert any(f.suffix=='.bak' for f in result.iterdir())
    assert b'ExperimentCompareV19Tab' in (target/'app.py').read_bytes()
    assert (target/'v19_compare_core.py').is_file()
    assert ins.install(repo,backup_root=tmp_path/'backups') is None


def test_preserve_unrecognized_existing_app(tmp_path):
    ins=get_module()
    repo,target=fake_repository(tmp_path,ins)
    (target/'app.py').write_text('local changes',encoding='utf-8')
    with pytest.raises(RuntimeError,match='独自変更'):
        ins.install(repo,backup_root=tmp_path/'backups')
    assert not (target/'v19_compare_core.py').exists()
