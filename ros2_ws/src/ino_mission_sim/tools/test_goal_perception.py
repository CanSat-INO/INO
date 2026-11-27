"""Goal association must respect position, ambiguity, and distinct viewpoints."""
import math
import unittest
import cv2
import numpy as np
from scipy.spatial.transform import Rotation
from goal_perception import GoalAssociation,cone_candidates,approach_plan,needs_goal_view,goal_view_angle
from ground_grid import TerrainGrid
from ground_world import load


class GoalTests(unittest.TestCase):
    def update(self,association,points,pose=(0,0,0),yaw=0,stamp=1):
        association.update([dict(relative=np.array(p,float)) for p in points],pose,
            Rotation.from_euler('z',yaw),Rotation.identity(),np.zeros(3),stamp)

    def test_same_color_outside_coordinate_prior_is_rejected(self):
        a=GoalAssociation((3.6,0))
        self.update(a,[(1.,0,0)])
        self.assertFalse(a.confirmed);self.assertEqual(0,a.candidates)

    def test_repeated_stationary_photo_does_not_confirm(self):
        a=GoalAssociation((3.6,0))
        self.update(a,[(3.6,0,0)]);self.update(a,[(3.6,0,0)],stamp=2)
        self.assertEqual(1,a.views);self.assertFalse(a.confirmed)

    def test_two_consistent_views_confirm_and_follow_map_correction(self):
        a=GoalAssociation((3.6,0))
        self.update(a,[(3.6,0,0)])
        self.update(a,[(3.5,0,0)],pose=(.1,0,0),stamp=2)
        self.assertTrue(a.confirmed)
        np.testing.assert_allclose(a.mapped(Rotation.identity(),np.array([.1,.2,0])),[3.7,.2])

    def test_two_nearby_cones_revoke_confirmation(self):
        a=GoalAssociation((3.6,0))
        self.update(a,[(3.6,0,0)]);self.update(a,[(3.5,0,0)],pose=(.1,0,0),stamp=2)
        self.update(a,[(3.6,0,0),(3.6,.3,0)],stamp=3)
        self.assertFalse(a.confirmed);self.assertEqual(0,a.views)
        self.assertEqual('ambiguous_cones_near_goal',a.reason)

    def test_basal_ray_recovers_projected_cone_position(self):
        # Pixel fixture generated from a known pinhole, not Gazebo object IDs.
        K=np.array([[500.,0,320],[0,500.,240],[0,0,1]])
        optical_to_body=np.array([[0,0,1],[-1,0,0],[0,-1,0.]])
        camera=np.array([.08,0,.18]);edge=np.array([.875,0,.03])
        projected=K@optical_to_body.T@(edge-camera);u,v=np.rint(projected[:2]/projected[2]).astype(int)
        image=np.zeros((480,640,3),np.uint8)
        cv2.fillConvexPoly(image,np.array([[u,v-100],[u-24,v],[u+24,v]],np.int32),(255,30,5))
        candidates=cone_candidates(image,K,optical_to_body,camera,Rotation.identity(),.125,.03)
        self.assertEqual(1,len(candidates));self.assertAlmostEqual(1.,candidates[0]['relative'][0],delta=.025)

    def test_plan_ends_outside_cone_and_inside_arrival_radius(self):
        cfg=load();g=TerrainGrid(cfg);g.seen[:]=True
        yy,xx=np.indices(g.shape);x=g.x0+(xx+.5)*g.res;y=g.y0+(yy+.5)*g.res
        g.blocked[(abs(x-3.6)<.125)&(abs(y)<.125)]=True
        path=approach_plan(g,(2.5,0),(3.6,0),.43)
        self.assertTrue(path)
        self.assertGreater(math.dist(path[-1],(3.6,0)),.395)
        self.assertLess(math.dist(path[-1],(3.6,0)),.5)

    def test_confirmed_goal_outside_arrival_does_not_interrupt_detour(self):
        # Actual v10 deadlock: the planner needed to turn away from a cone at
        # the image edge, but the old view gate immediately turned it back.
        self.assertFalse(needs_goal_view(.473,.47,True,False))
        self.assertTrue(needs_goal_view(.46,.47,True,False))
        self.assertTrue(needs_goal_view(.52,.47,False,False))

    def test_goal_view_uses_shortest_turn_instead_of_full_circle(self):
        angle=goal_view_angle((3.423,.415),(3.6,0),0.)
        self.assertAlmostEqual(-math.radians(10),angle)
        angle=goal_view_angle((0,0),(-1,-.01),math.pi-.01)
        self.assertIsNone(angle)

    def test_goal_view_respects_camera_yaw_and_requires_another_view(self):
        self.assertIsNone(goal_view_angle((0,0),(1,1),0.,math.pi/4))
        self.assertAlmostEqual(math.radians(10),goal_view_angle((0,0),(1,0),0.,candidates=1))
        self.assertIsNone(goal_view_angle((0,0),(1,0),0.,candidates=2))

    def test_side_clipped_cone_cannot_shift_goal_range(self):
        K=np.array([[500.,0,320],[0,500.,240],[0,0,1]])
        optical_to_body=np.array([[0,0,1],[-1,0,0],[0,-1,0.]])
        image=np.zeros((480,640,3),np.uint8)
        cv2.fillConvexPoly(image,np.array([[0,180],[0,330],[25,330]],np.int32),(255,30,5))
        self.assertFalse(cone_candidates(image,K,optical_to_body,np.array([.08,0,.18]),Rotation.identity(),.1,.045))


if __name__=='__main__':unittest.main()
