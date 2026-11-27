import hashlib,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
import yaml
from design_config import ROOT
from shared_camera import CAMERA
from mission_world import generate
from mission_config import load_mission

class MissionWorldTest(unittest.TestCase):
    def test_separate_world_does_not_change_camera_experiments(self):
        protected=[CAMERA/'config/design.yaml',CAMERA/'config/stereo.rviz',CAMERA/'launch/stereo.launch.py']
        before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in protected]
        cfg=yaml.safe_load((ROOT/'config/firmware/mission.yaml').read_text())
        with tempfile.TemporaryDirectory(prefix='cansat-mission-test-') as folder:
            sdf=ET.parse(generate(cfg,folder));world=sdf.getroot().find('world');self.assertEqual(world.get('name'),'mission_lab')
            model=world.find("model[@name='cansat']");self.assertEqual(float(model.find('pose').text.split()[2]),10.)
            topics=[p.findtext('topic') for p in model.findall('plugin')]
            self.assertIn('/mission/plant/cmd_vel',topics);self.assertNotIn('/cmd_vel',topics)
        self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in protected])
    def test_descent_release_height_and_yaw_and_gui(self):
        cfg=load_mission(ROOT/'config/firmware/descent.yaml');cfg['release_yaw_deg']=90.
        with tempfile.TemporaryDirectory(prefix='cansat-descent-world-') as folder:
            sdf=ET.parse(generate(cfg,folder));pose=sdf.find("world/model[@name='cansat']/pose").text.split()
            self.assertEqual(float(pose[2]),30.);self.assertAlmostEqual(float(pose[5]),1.5707963267948966)
            gui=Path(folder)/'gui.config'
            if gui.exists():
                self.assertIn('<follow_target>cansat</follow_target>',gui.read_text());self.assertIn('-3 -3 32',gui.read_text())
if __name__=='__main__':unittest.main()
