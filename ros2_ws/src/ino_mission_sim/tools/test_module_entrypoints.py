"""Check each ROS child in a fresh interpreter, not unittest import order."""
import subprocess,sys,unittest
from pathlib import Path

class ChildImports(unittest.TestCase):
 def test_required_children_import_standalone(self):
  root=Path(__file__).resolve().parent
  for name in ('ground_capture','ground_odometry','ground_navigation','ground_evaluate','mission_node','mission_ready'):
   with self.subTest(module=name):subprocess.run([sys.executable,'-c','import '+name],cwd=root,check=True,timeout=20,capture_output=True)
if __name__=='__main__':unittest.main()
