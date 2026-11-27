import unittest
from types import SimpleNamespace as NS
import numpy as np
from scipy.spatial.transform import Rotation
from ground_observations import ObservationHistory


def pose(x,y=0,z=0):
    return NS(position=NS(x=x,y=y,z=z),orientation=NS(x=0,y=0,z=0,w=1))


class ObservationTests(unittest.TestCase):
    def test_each_cloud_uses_its_own_optimized_pose(self):
        history=ObservationHistory()
        history.append(1,np.array([[1.,0,0]]))
        history.append(2,np.array([[1.4,0,0]]))
        history.update([NS(id=1,stamp=1,pose=pose(0)),NS(id=2,stamp=2,pose=pose(.4))],
                       [1,2],[pose(0),pose(0)])
        clouds=list(history.clouds(Rotation.identity(),np.zeros(3)))
        np.testing.assert_allclose(clouds[0],clouds[1])
        np.testing.assert_allclose(clouds[0],[[1.,0,0]])

    def test_fallback_and_new_optimization_rebuild(self):
        history=ObservationHistory();history.append(1,np.array([[1.,0,0]]))
        np.testing.assert_allclose(list(history.clouds(Rotation.identity(),np.array([.2,0,0])))[0],[[1.2,0,0]])
        history.update([NS(id=1,stamp=1,pose=pose(0))],[1],[pose(.1)])
        self.assertTrue(history.dirty);history.dirty=False
        history.update([], [1],[pose(.1)])
        self.assertFalse(history.dirty)
        history.update([], [1],[pose(.2)])
        self.assertTrue(history.dirty)


if __name__=='__main__':unittest.main()
