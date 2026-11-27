"""Behavior checks for traversability, planning, and contact-world separation."""
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np
from ground_world import load,generate
from ground_grid import TerrainGrid


class TerrainTests(unittest.TestCase):
    def setUp(self):self.cfg=load();self.grid=TerrainGrid(self.cfg)

    def fill(self,function):
        yy,xx=np.indices(self.grid.shape)
        x=self.grid.x0+(xx+.5)*self.grid.res;y=self.grid.y0+(yy+.5)*self.grid.res
        self.grid.height[:]=function(x,y);self.grid.seen[:]=True;self.grid.classify()

    def test_gentle_slope_and_low_step_are_passable(self):
        self.fill(lambda x,y:.1*x)
        self.assertFalse(self.grid.blocked[20:50,20:50].any())
        self.fill(lambda x,y:np.where(x>1.,.015,0.))
        self.assertFalse(self.grid.blocked[10:-10,10:-10].any())

    def test_high_step_is_blocked_and_planner_goes_around(self):
        self.fill(lambda x,y:np.where((abs(x-1)<.2)&(abs(y)<.3),.2,0.))
        self.assertTrue(self.grid.blocked[self.grid.cell(.825,0.)])
        plan=self.grid.plan((0.,0.),(2.,0.));self.assertTrue(plan)
        self.assertGreater(max(abs(y) for x,y in plan),.45)
        costs=self.grid.planning_cost()
        self.assertTrue(all(np.isfinite(costs[self.grid.cell(x,y)]) for x,y in plan))

    def test_unknown_cannot_authorize_driving(self):
        self.assertTrue(self.grid.plan((0.,0.),(2.,0.)))
        self.assertFalse(self.grid.observed_segment((0.,0.),(.4,0.)))

    def test_blocked_corridor_has_no_path(self):
        self.fill(lambda x,y:np.where(abs(x-1)<.15,.2,0.))
        self.assertEqual([],self.grid.plan((0.,0.),(2.,0.)))

    def test_can_leave_new_margin_without_approaching_obstacle(self):
        self.fill(lambda x,y:np.where((abs(x-1)<.2)&(abs(y)<.3),.2,0.))
        from scipy.ndimage import distance_transform_edt
        distance=distance_transform_edt(~self.grid.blocked)*self.grid.res
        candidates=np.argwhere((distance>=self.cfg['footprint_radius_m'])&(distance<self.cfg['footprint_radius_m']+self.cfg['safety_margin_m']))
        cell=next(tuple(c) for c in candidates if self.grid.xy(c)[0]<.6 and abs(self.grid.xy(c)[1])<.1)
        start=self.grid.xy(cell)
        self.assertFalse(np.isfinite(self.grid.planning_cost()[cell]))
        path=self.grid.plan(start,(0.,0.));self.assertTrue(path)
        self.assertTrue(all(distance[self.grid.cell(x,y)]>=distance[cell]-1e-9 for x,y in path))

    def test_real_blocked_start_is_not_cleared(self):
        self.fill(lambda x,y:np.where(abs(x-1)<.15,.2,0.))
        self.assertEqual([],self.grid.plan((.825,0.),(0.,0.)))

    def test_cone_square_base_corner_clearance(self):
        from review_ground import clearance
        obstacles=dict(cones=[[0.,0.]],cone_base_m=.25,boxes=[])
        self.assertAlmostEqual(clearance((.3,.3),obstacles,.17),2**.5*.175-.17)
        self.assertLess(clearance((.2,.2),obstacles,.17),0.)

    def test_occupied_center_fills_blind_spot_but_preserves_hazards(self):
        self.grid.occupy((2.,0.,0.))
        self.assertTrue(self.grid.seen[self.grid.cell(2.,0.)])
        self.assertFalse(self.grid.seen[self.grid.cell(2.2,0.)])
        cell=self.grid.cell(2.,0.);self.grid.blocked[cell]=True;self.grid.cost[cell]=100
        self.grid.occupy((2.,0.,0.));self.assertTrue(self.grid.blocked[cell]);self.assertEqual(100,self.grid.cost[cell])

    def test_contact_model_and_stop_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            file=generate(self.cfg,folder);world=ET.parse(file).getroot().find('world')
            robot=world.find("model[@name='cansat']")
            names=[p.get('name') for p in robot.findall('plugin')]
            self.assertFalse(any('VelocityControl' in n for n in names))
            self.assertEqual(2,sum('TrackController' in n for n in names))
            self.assertEqual('true',robot.find("link[@name='base_link']/gravity").text)
            import yaml
            from pathlib import Path
            cfg=yaml.safe_load((Path(folder)/'effective.yaml').read_text())
            self.assertEqual('stop',cfg['capture']['mode'])


if __name__=='__main__':unittest.main()
