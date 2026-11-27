import math
import unittest
from ground_motion import TurnProgress,TerrainHeadingLock,arc_points,next_path_cell,CornerTarget
from scipy.spatial.transform import Rotation


class MotionTests(unittest.TestCase):
    def test_repeated_failed_turns_require_recovery(self):
        monitor=TurnProgress()
        for _ in range(2):monitor.begin(0,math.radians(10));monitor.finish(.001)
        self.assertEqual(2,monitor.blocked)
        monitor.begin(0,math.radians(10));monitor.finish(.1)
        self.assertEqual(0,monitor.blocked)

    def test_crossing_yaw_wrap_is_a_successful_turn(self):
        monitor=TurnProgress();monitor.begin(math.radians(179),math.radians(10));monitor.finish(math.radians(-172))
        self.assertEqual(0,monitor.blocked)

    def test_forward_reverse_arcs_remain_short(self):
        forward=arc_points((0,0),0,.03,.14,1.)
        reverse=arc_points((0,0),0,-.03,.14,1.)
        self.assertGreater(forward[-1][0],0);self.assertLess(reverse[-1][0],0)
        self.assertLess(math.dist(forward[0],forward[-1]),.031)

    def test_crossing_heading_stays_locked_over_flat_top_until_exit(self):
        lock=TerrainHeadingLock(.25)
        lock.update((0,0),Rotation.identity());self.assertFalse(lock.active)
        lock.update((.05,0),Rotation.from_euler('y',4,degrees=True));self.assertTrue(lock.active)
        lock.update((.15,0),Rotation.identity());self.assertTrue(lock.active)
        lock.update((.2,0),Rotation.from_euler('y',-4,degrees=True));self.assertTrue(lock.active)
        lock.update((.4,0),Rotation.identity());self.assertTrue(lock.active)
        lock.update((.46,0),Rotation.identity());self.assertFalse(lock.active)

    def test_local_target_keeps_first_corner_instead_of_cutting_it(self):
        path=[(0.,0.),(.05,0.),(.05,.05),(.05,.1),(.05,.2),(.05,.3)]
        self.assertEqual((.05,0.),next_path_cell(path,(.01,.01),.05))

    def test_corner_alignment_keeps_target_until_cell_is_reached(self):
        corner=CornerTarget();path=[(0,0),(.05,0),(.05,.05),(.05,.3)]
        corner.choose(path,(.01,.01),.05)
        self.assertEqual((.05,0),corner.current((.01,.01),.05,lambda a,b:True))
        self.assertIsNone(corner.current((.048,0),.05,lambda a,b:True))
        corner.choose(path,(.01,.01),.05)
        self.assertIsNone(corner.current((.01,.01),.05,lambda a,b:False))


if __name__=='__main__':unittest.main()
