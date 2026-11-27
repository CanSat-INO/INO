import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from mission_bridge import PACKAGE,results

class MissionBridgeTests(unittest.TestCase):
 def test_landing_is_not_a_full_mission_goal(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder=root/'logs/run';folder.mkdir(parents=True)
   (folder/'result.json').write_text(json.dumps({'reason':'landed','goal_stopped':False,'controller_kind':'connection_example_only','landing':{'vertical_speed_mps':4.2}}))
   row=results(root)[0];self.assertEqual(row['state'],'着地（降下のみ）');self.assertEqual(row['controller'],'connection_example_only')
   (folder/'result.json').write_text(json.dumps({'passed':False}));self.assertEqual(results(root)[0]['state'],'未達／要確認')

 def test_cpp_adapter_uses_inputs_and_records_header_provenance(self):
  repo=Path(__file__).resolve().parents[3]
  spec=importlib.util.spec_from_file_location('ino_native_builder',repo/'cansat/sil/build_controller.py')
  builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);header=root/'policy.hpp';header.write_text('inline double decide(double altitude) { return altitude>1 ? 0.25 : 0; }')
   source=root/'adapter.cpp';source.write_text('#include "sim_port.hpp"\n#include "policy.hpp"\nint main(){cansat_sim::Sensors s;cansat_sim::Actuators a;while(cansat_sim::wait(100,a,s)){a.left=decide(s.altitude_m);a.right=-a.left;a.phase=5;}}')
   original=source.read_bytes();binary=builder.build([source],root/'build/controller',contract=PACKAGE/'firmware/sil')
   packet='100 5 20 1000 35 139 90 0 0 0 - 31 100 100 100 100 100\nSTOP\n'
   lines=subprocess.check_output([str(binary)],input=packet,text=True,timeout=5).splitlines()
   self.assertEqual(lines[1].split()[:6],['WAIT2','100','0.25','-0.25','0','5'])
   m=json.loads((binary.parent/'manifest.json').read_text());self.assertIn(str(header),m['dependencies']);self.assertFalse(m['hardware_emulated']);self.assertEqual(source.read_bytes(),original)
   bad=root/'firmware.ino';bad.write_text('void loop(){}')
   with self.assertRaises(ValueError):builder.build([bad],root/'bad',contract=PACKAGE/'firmware/sil')

if __name__=='__main__':unittest.main()
