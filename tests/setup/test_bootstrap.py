import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ino_ros_bootstrap',ROOT/'scripts/install_ros2.py')
ros=importlib.util.module_from_spec(spec);spec.loader.exec_module(ros)


class BootstrapTests(unittest.TestCase):
 def test_unsupported_os_rejected_before_commands(self):
  with patch.object(ros,'os_release',return_value={'ID':'ubuntu','VERSION_ID':'22.04'}),patch.object(ros.subprocess,'run') as run,patch.object(ros.urllib.request,'urlopen') as fetch:
   with self.assertRaises(RuntimeError):ros.main([])
   run.assert_not_called();fetch.assert_not_called()

 def test_only_enabled_binary_ros_repository_is_reused(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'sources.list.d').mkdir()
   f=root/'sources.list';f.write_text('# deb https://packages.ros.org/ros2/ubuntu noble main\ndeb-src https://packages.ros.org/ros2/ubuntu noble main\n')
   self.assertFalse(ros.source_present(root))
   g=root/'sources.list.d/ros2.sources';g.write_text('Types: deb\nURIs: https://packages.ros.org/ros2/ubuntu\nEnabled: no\n')
   self.assertFalse(ros.source_present(root));g.write_text(g.read_text().replace('Enabled: no','Enabled: yes'));self.assertTrue(ros.source_present(root))

 def test_cold_ros_dry_run_never_downloads_or_installs(self):
  with patch.object(ros,'os_release',return_value={'ID':'ubuntu','VERSION_ID':'24.04'}),patch.object(ros,'source_present',return_value=False),patch.object(ros.subprocess,'check_output',return_value='amd64'),patch.object(ros.subprocess,'run') as run,patch.object(ros.urllib.request,'urlopen') as fetch:
   self.assertEqual(ros.main(['--dry-run']),0);run.assert_not_called();fetch.assert_not_called()

 def test_lyrical_cold_setup_selects_resolute_and_lyrical(self):
  import contextlib,io
  with patch.object(ros,'os_release',return_value={'ID':'ubuntu','VERSION_ID':'26.04'}),patch.object(ros,'source_present',return_value=False),patch.object(ros.subprocess,'check_output',return_value='amd64'),contextlib.redirect_stdout(io.StringIO()) as output:
   self.assertEqual(ros.main(['--dry-run']),0)
  self.assertIn('ros2-apt-source_1.3.0.resolute_all.deb',output.getvalue())
  self.assertIn('ros-lyrical-ros-base',output.getvalue())
  self.assertNotIn('ros-jazzy',output.getvalue())

 def test_existing_repository_is_not_replaced(self):
  with patch.object(ros,'os_release',return_value={'ID':'ubuntu','VERSION_ID':'24.04'}),patch.object(ros,'source_present',return_value=True),patch.object(ros.subprocess,'check_output',return_value='amd64'),patch.object(ros.subprocess,'run') as run,patch.object(ros.urllib.request,'urlopen') as fetch:
   ros.main([]);fetch.assert_not_called()
   self.assertFalse(any('add-apt-repository' in call.args[0] for call in run.call_args_list))

 def test_corrupt_download_is_rejected(self):
  with self.assertRaises(RuntimeError):ros.verified(b'not the official package')

 def clone_fixture(self,root):
  import shutil
  (root/'scripts').mkdir(parents=True)
  for name in ['setup.sh','install_ros2.py','doctor.py','doctor.sh']:shutil.copy2(ROOT/'scripts'/name,root/'scripts'/name)
  for name in ['requirements-gui.txt','requirements-dev.txt']:shutil.copy2(ROOT/name,root/name)

 def test_dry_run_from_space_path_writes_no_files(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'clone with spaces';self.clone_fixture(root)
   before={str(p.relative_to(root)) for p in root.rglob('*')}
   proc=subprocess.run(['bash',str(root/'scripts/setup.sh'),'--skip-system-packages','--dry-run'],cwd='/tmp',capture_output=True,text=True)
   self.assertEqual(proc.returncode,0,proc.stderr);self.assertIn(str(root),proc.stdout.replace('\\ ',' '))
   self.assertEqual(before,{str(p.relative_to(root)) for p in root.rglob('*')})

 def test_symlinked_venv_is_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'clone';self.clone_fixture(root);external=Path(d)/'existing';external.mkdir();marker=external/'keep';marker.write_text('user data');(root/'.venv').symlink_to(external,target_is_directory=True)
   proc=subprocess.run(['bash',str(root/'scripts/setup.sh'),'--skip-system-packages','--dry-run'],capture_output=True,text=True)
   self.assertEqual(proc.returncode,2);self.assertIn('symlinked',proc.stderr);self.assertEqual(marker.read_text(),'user data')

 def test_actual_windows_wrapper_recognizes_wsl_unc_paths(self):
  import re
  source=(ROOT/'camera-simu.ps1').read_text()
  pattern=re.search(r"\$root -match '([^']+)'",source).group(1)
  for prefix in [r'\\wsl.localhost\Ubuntu',r'\\wsl$\Ubuntu-24.04']:
   match=re.match(pattern,prefix+r'\home\member\INO with spaces')
   self.assertIsNotNone(match)
   self.assertEqual(match.group(2).replace('\\','/'),'/home/member/INO with spaces')
  self.assertIsNone(re.match(pattern,r'C:\Users\member\INO'))

 def test_fresh_clone_doctor_reports_missing_files_without_writes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'clone';self.clone_fixture(root);before={str(p.relative_to(root)) for p in root.rglob('*')}
   proc=subprocess.run(['/usr/bin/python3',str(root/'scripts/doctor.py'),'--lab-only','--json'],capture_output=True,text=True)
   self.assertEqual(proc.returncode,1,proc.stderr);result=json.loads(proc.stdout);self.assertFalse(result['passed'])
   self.assertTrue(any(r['name']=='GUI venv' and r['status']=='FAIL' for r in result['checks']))
   self.assertEqual(before,{str(p.relative_to(root)) for p in root.rglob('*')})

if __name__=='__main__':unittest.main()
