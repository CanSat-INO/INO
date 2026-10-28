#!/usr/bin/env python3
"""Read-only v23 release diagnostics. No user code or attached C++ is executed."""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REQUIRED = [
 'app.py','module_navigation.py','navigation_search_v13_5.py',
 'v14_host_runner.py','v15_sensor_core.py','v16_experiment_core.py',
 'v17_phase_core.py','v18_bus_core.py','v19_compare_core.py',
 'v20_workflow_core.py','v21_quality_core.py',
 'v15_sensor_tab.py','v16_experiment_tab.py','v17_phase_tab.py',
 'v18_bus_tab.py','v19_compare_tab.py','v20_workflow_tab.py',
 'v21_quality_tab.py', 'launch_v13_4.sh'
]

def inspect(root):
    findings=[]
    for name in REQUIRED:
        p=root/name
        if p.is_symlink() or not p.is_file():
            findings.append({'status':'FAIL','area':'files','item':name,'detail':'ファイルが存在しないかリンクです'})
            continue
        try:
            if name.endswith('.py'):
                ast.parse(p.read_text(encoding='utf-8-sig'), filename=name)
            findings.append({'status':'PASS','area':'files','item':name,'detail':'存在・構文OK' if name.endswith('.py') else '存在OK'})
        except (SyntaxError,UnicodeError,OSError) as exc:
            findings.append({'status':'FAIL','area':'files','item':name,'detail':type(exc).__name__})
    return findings

def main(argv=None):
    p=argparse.ArgumentParser(description='v23 読み取り専用リリース診断')
    p.add_argument('--repo',type=Path,default=Path.home()/'INO-module-lab')
    p.add_argument('--output',type=Path,help='JSON結果の保存先 (任意)')
    a=p.parse_args(argv)
    root=a.repo.expanduser().resolve()/'tools'/'module_test_lab'
    if not root.is_dir():p.error('tools/module_test_lab がありません')
    findings=inspect(root)
    report={'version':'v23','timestamp_utc':datetime.now(timezone.utc).isoformat(),
       'scope':'file-presence-and-python-syntax-only','findings':findings,
       'summary':{'passed':sum(x['status']=='PASS' for x in findings),
                  'failed':sum(x['status']=='FAIL' for x in findings)},
       'not_verified':['GUI操作','日本語IME','実験記録の読み書き','C++実行','ESP32-S3実機','センサー精度','通信安全性']}
    print(f"v23構成・構文診断: PASS {report['summary']['passed']} / FAIL {report['summary']['failed']}")
    for x in findings:
        print(f"  {x['status']:4s} {x['item']}: {x['detail']}")
    if a.output:
        target=a.output.expanduser().absolute()
        if target.exists():p.error('既存のレポートを上書きしません。別の名前を指定してください')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('保存:',target)
    return int(report['summary']['failed']>0)

if __name__=='__main__':sys.exit(main())
