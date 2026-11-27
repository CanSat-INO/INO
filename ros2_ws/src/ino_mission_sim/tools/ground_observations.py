"""Reproject each measured cloud with its own SLAM keyframe correction.

Moving every old cloud by the *latest* map-to-odom correction would smear
terrain when odometry drift changes over a run. No simulator state is used.
"""
from collections import deque
import numpy as np
from scipy.spatial.transform import Rotation


def pose_transform(pose):
    q=pose.orientation;p=pose.position
    return Rotation.from_quat([q.x,q.y,q.z,q.w]),np.array([p.x,p.y,p.z])


class ObservationHistory:
    def __init__(self,limit=100):
        self.records=deque(maxlen=limit);self.anchors={};self.optimized={};self.dirty=False

    def append(self,stamp,points):
        self.records.append((stamp,np.asarray(points).copy()));self.dirty=True

    def update(self,nodes,identifiers,poses):
        for node in nodes:
            if node.id>0:self.anchors[node.id]=(node.stamp,*pose_transform(node.pose))
        updated={index:pose_transform(pose) for index,pose in zip(identifiers,poses) if index>0}
        changed=set(updated)!=set(self.optimized)
        if not changed:
            for index,(rotation,position) in updated.items():
                old_rotation,old_position=self.optimized[index]
                if np.linalg.norm(position-old_position)>.005 or (rotation*old_rotation.inv()).magnitude()>.003:
                    changed=True;break
        self.optimized=updated;self.dirty|=changed

    def clouds(self,fallback_rotation,fallback_translation):
        anchors=[(stamp,raw_rotation,raw_position,*self.optimized[index])
                 for index,(stamp,raw_rotation,raw_position) in self.anchors.items() if index in self.optimized]
        for stamp,points in self.records:
            if anchors:
                _,raw_rotation,raw_position,optimized_rotation,optimized_position=min(anchors,key=lambda anchor:abs(anchor[0]-stamp))
                rotation=optimized_rotation*raw_rotation.inv()
                translation=optimized_position-rotation.apply(raw_position)
            else:rotation=fallback_rotation;translation=fallback_translation
            yield rotation.apply(points)+translation
