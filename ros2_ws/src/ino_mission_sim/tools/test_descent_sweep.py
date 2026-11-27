import unittest
from mission_config import load_mission
from compare_descent import simulate
from sweep_descent import evaluate_grid,ROOT

class SweepTests(unittest.TestCase):
    def test_terminal_speed_alone_does_not_pass(self):
        base=load_mission(ROOT/'config/firmware/descent.yaml')
        grid=dict(diameter_m=[.76],trigger_time_s=[1.],opening_s=[1.5],wind_mps=[6.],max_vertical_speed_mps=5.)
        rows,candidates=evaluate_grid(base,grid)
        self.assertLess(rows[0]['precontact_vertical_mps'],5.)
        self.assertGreater(rows[0]['peak_descent_mps'],5.)
        self.assertFalse(candidates[0]['passes_filter'])
    def test_time_limit_in_air_is_not_ground_contact(self):
        base=load_mission(ROOT/'config/firmware/descent.yaml');base['duration_s']=.1
        rows,_=simulate(base);self.assertGreater(rows[-1,3],29.);self.assertEqual(rows[-1,-1],0.)
