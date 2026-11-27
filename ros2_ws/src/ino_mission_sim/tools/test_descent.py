"""Analytical and scenario checks for the flight model, independent of Gazebo."""
from copy import deepcopy
from pathlib import Path
import math
import unittest
import numpy as np
from descent_dynamics import Descent,world_to_body
from mission_config import load_mission

ROOT=Path(__file__).resolve().parents[1]

class DescentTests(unittest.TestCase):
    def config(self):return load_mission(ROOT/'config/firmware/descent.yaml')
    def test_freefall_matches_gravity_without_drag(self):
        cfg=self.config();cfg['descent']['body_cda_m2']=0.;cfg['descent']['parachute']['failure']=True
        f=Descent(cfg);v,a=f.advance(1.,1.,100.)
        np.testing.assert_allclose(v,[0,0,-9.81],atol=1e-10);np.testing.assert_allclose(a,[0,0,-9.81],atol=1e-10)
    def test_open_chute_converges_to_analytic_terminal_velocity(self):
        cfg=self.config();cfg['descent']['wind']['mean_enu_mps']=[0,0,0]
        cfg['descent']['parachute'].update(trigger_time_s=0.,opening_s=0.)
        f=Descent(cfg)
        for i in range(1000):f.advance((i+1)*.02,.02,1000.)
        terminal=math.sqrt(2*f.mass*9.81/(f.rho*(f.body_cda+f.full_cda)))
        self.assertAlmostEqual(-f.velocity[2],terminal,places=5)
    def test_area_ramp_delay_and_partial_opening(self):
        cfg=self.config();cfg['descent']['parachute'].update(trigger='command',delay_s=1.,opening_s=2.,max_fraction=.8)
        f=Descent(cfg);f.deploy(2.)
        self.assertEqual(f.opening(2.5,20),0.);self.assertAlmostEqual(f.opening(4.,20),.4);self.assertAlmostEqual(f.opening(5.,20),.8)
    def test_altitude_trigger_requires_descent(self):
        cfg=self.config();cfg['descent']['parachute']['trigger']='altitude';f=Descent(cfg)
        f.velocity[2]=1.;f.opening(1.,20.);self.assertIsNone(f.triggered_at)
        f.velocity[2]=-1.;f.opening(2.,24.);self.assertEqual(f.triggered_at,2.)
    def test_command_and_failure_and_detachment(self):
        cfg=self.config();cfg['descent']['parachute']['trigger']='command';f=Descent(cfg)
        self.assertEqual(f.opening(10.,10.),0.);f.deploy(10.);self.assertEqual(f.opening(12.,10.),1.)
        f.detach();self.assertEqual(f.opening(13.,10.),0.);self.assertEqual(f.stage,'detached')
        cfg['descent']['parachute']['failure']=True;failed=Descent(cfg);failed.deploy(0.);self.assertEqual(failed.opening(10.,10.),0.)
    def test_wind_drives_horizontal_velocity_towards_air_velocity(self):
        cfg=self.config();cfg['descent']['parachute'].update(trigger_time_s=0.,opening_s=0.);f=Descent(cfg)
        for i in range(1000):f.advance((i+1)*.02,.02,1000.)
        self.assertAlmostEqual(f.velocity[0],6.,places=5);self.assertAlmostEqual(f.velocity[1],0.,places=8)
    def test_gust_interval_and_reproducible_fluctuations(self):
        cfg=self.config();cfg['descent']['wind']['gusts']=[dict(start_s=2.,duration_s=2.,delta_enu_mps=[4.,2.,0.])]
        f=Descent(cfg);np.testing.assert_allclose(f.wind(2.),[6,0,0]);np.testing.assert_allclose(f.wind(3.),[10,2,0]);np.testing.assert_allclose(f.wind(4.),[6,0,0])
        cfg['descent']['wind']['turbulence_std_mps']=.4;a=Descent(cfg);b=Descent(cfg)
        np.testing.assert_array_equal(a.wind(3.1),b.wind(3.1));self.assertGreater(np.linalg.norm(a.wind(3.1)-f.wind(3.1)),.01)
    def test_world_wind_is_independent_of_release_yaw(self):
        np.testing.assert_allclose(world_to_body(np.array([6.,0.,-4.]),math.pi/2),[0,-6,-4],atol=1e-12)
    def test_substeps_converge_with_different_controller_intervals(self):
        cfg=self.config();runs=[]
        for dt in [.01,.02,.05]:
            f=Descent(deepcopy(cfg))
            for i in range(round(4/dt)):f.advance((i+1)*dt,dt,1000.)
            runs.append(f.velocity)
        np.testing.assert_allclose(runs[0],runs[2],atol=.04)
    def test_invalid_inputs_rejected(self):
        cfg=self.config();cfg['descent']['parachute']['opening_s']=-1
        with self.assertRaises(ValueError):Descent(cfg)
    def test_config_inheritance_preserves_original_baseline(self):
        cfg=self.config();baseline=load_mission(ROOT/'config/firmware/mission.yaml')
        self.assertEqual(cfg['release_height_m'],30.);self.assertEqual(baseline['release_height_m'],10.);self.assertNotIn('descent',baseline)
        gust=load_mission(ROOT/'config/firmware/descent_gust.yaml');self.assertEqual(gust['descent']['wind']['mean_enu_mps'],[6.,0.,0.]);self.assertEqual(len(gust['descent']['wind']['gusts']),1)

if __name__=='__main__':unittest.main()
