"""Check epipolar geometry independently by projecting 3D points."""
import unittest
import numpy as np
from design_config import load,rig

class StereoGeometryTests(unittest.TestCase):
    def test_rectified_rows_agree_for_adjusted_mounts(self):
        for overrides in [[],['camera.toe_in_deg=5','camera.pitch_down_deg=30'],['camera.yaw_deg=12','camera.roll_deg=5','camera.right_height_delta_m=0.01','camera.right_forward_delta_m=0.015']]:
            g=rig(load(overrides=overrides))
            for point in [np.array([1.,.2,.1]),np.array([2.,-.3,.3]),np.array([.7,0,.05])]:
                rows=[]
                for side,i in [('left',1),('right',2)]:
                    local=g['raw_rotations'][side].T@(point-g['positions'][side])
                    rect=g[f'R{i}']@local
                    pixels=g[f'P{i}'][:3,:3]@rect
                    rows.append(pixels[1]/pixels[2])
                self.assertAlmostEqual(rows[0],rows[1],places=7)
            self.assertAlmostEqual(abs(g['P2'][0,3]/g['P2'][0,0]),np.linalg.norm(g['T']),places=8)

    def test_unrepresentable_skew_is_rejected(self):
        with self.assertRaises(ValueError):load(overrides=['capture.mode=sequential','capture.skew_s=0.01','camera.fps=10'])

    def test_fractional_image_resolution_is_rejected(self):
        with self.assertRaises(ValueError):load(overrides=['camera.width=640.5'])

if __name__=='__main__':unittest.main()
