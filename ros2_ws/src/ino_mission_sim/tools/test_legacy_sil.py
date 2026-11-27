"""Native execution verifies source behavior and explicit simulation adaptations."""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class LegacyTests(unittest.TestCase):
    def probe(self,profile):
        exe=ROOT/'firmware/sil/build'/profile/'legacy_sil'
        if not exe.exists():self.skipTest('Run tools/build_legacy_sil.py for both profiles first')
        return dict(x.split('=',1) for x in subprocess.check_output([str(exe),'--probe'],text=True).splitlines())
    def test_original_retains_landing_and_stuck_edge_cases(self):
        r=self.probe('original');self.assertEqual(r['stationary_before_release_landed'],'1');self.assertEqual(r['stationary_stuck_detected'],'0')
    def test_original_goal_does_not_stop_but_mission_profile_does(self):
        old=self.probe('original');new=self.probe('mission')
        self.assertEqual(old['at_goal_phase'],'6');self.assertNotEqual(old['at_goal_action'],'0');self.assertEqual(new['at_goal_action'],'0')
    def test_original_rgb565_algorithm_runs(self):
        r=self.probe('original');self.assertAlmostEqual(float(r['red_ratio']),10.);self.assertEqual(int(r['red_x']),79)
    def test_original_motor_direction_and_stop(self):
        r=self.probe('original');self.assertEqual(r['forward_action'],'1');self.assertEqual(r['stop_action'],'0')
    def test_future_controller_contract(self):
        exe=ROOT/'firmware/sil/build/stop_controller'
        if not exe.exists():self.skipTest('Build stop_controller_example.cpp first')
        proc=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(),'WAIT2 100 0 0 0 0')
            proc.stdin.write('100 10 20 1013.25 30 130 90 0 0 0 -\n');proc.stdin.flush()
            self.assertEqual(proc.stdout.readline().strip(),'WAIT2 100 0 0 0 0')
            proc.stdin.write('STOP\n');proc.stdin.flush();self.assertEqual(proc.wait(timeout=2),0)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
            proc.stdin.close();proc.stdout.close()
    def test_future_controller_reads_validity_and_clears_it_for_old_packets(self):
        with tempfile.TemporaryDirectory(prefix='cansat-port-test-') as folder:
            folder=Path(folder);source=folder/'port.cpp';binary=folder/'port'
            source.write_text('''#include "sim_port.hpp"
int main(){
 cansat_sim::Sensors in;cansat_sim::Actuators out;
 for(int i=0;i<2;++i){
  if(!cansat_sim::wait(0,out,in))return 3;
  std::cout<<"META "<<in.valid_mask<<" "<<in.camera_ms<<std::endl;
 }
}
''')
            subprocess.run(['g++','-std=c++17','-I'+str(ROOT/'firmware/sil'),str(source),'-o',str(binary)],check=True)
            modern='100 10 20 1013.25 30 130 90 0 0 0 - 31 100 100 100 100 100\n'
            legacy='200 10 20 1013.25 30 130 90 0 0 0 -\n'
            output=subprocess.check_output([str(binary)],input=modern+legacy,text=True).splitlines()
            self.assertEqual(output,['WAIT2 0 0 0 0 0','META 31 100','WAIT2 0 0 0 0 0','META 0 -1'])
if __name__=='__main__':unittest.main()
