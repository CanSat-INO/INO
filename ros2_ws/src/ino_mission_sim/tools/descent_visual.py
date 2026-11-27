"""Schematic canopy and native Gazebo screenshots, independent of plant timing.

Use the same atomic status file as the progress panel so short drops do not
depend on discovery of an additional ROS display subscriber.
"""
import argparse,io,json,math,os,time
from pathlib import Path
from PIL import Image

if os.environ.get("ROS_DISTRO") == "lyrical":
    from gz.transport15 import Node
    from gz.msgs.marker_pb2 import Marker
    from gz.msgs.marker_v_pb2 import Marker_V
    from gz.msgs.boolean_pb2 import Boolean
    from gz.msgs.stringmsg_pb2 import StringMsg
    from gz.msgs.cameratrack_pb2 import CameraTrack
else:
    from gz.transport13 import Node
    from gz.msgs10.marker_pb2 import Marker
    from gz.msgs10.marker_v_pb2 import Marker_V
    from gz.msgs10.boolean_pb2 import Boolean
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.cameratrack_pb2 import CameraTrack

class Visual:
    def __init__(self,output,follow=True):
        self.gz=Node();self.connected=False;self.output=Path(output);self.shots=set();self.last=None
        self.follow=follow;self.follow_started=False;self.camera_ready_at=0.
        self.follow_pub=self.gz.advertise('/gui/track',CameraTrack) if follow else None

    def show(self,data):
        flight=data.get('descent')
        if not flight or 'position_enu_m' not in data:return
        if self.last==data['elapsed_s']:return
        self.last=data['elapsed_s'];x,y,z=data['position_enu_m'];fraction=flight['open_fraction']
        marker=Marker();marker.ns='cansat_descent_canopy';marker.id=2
        marker.action=Marker.ADD_MODIFY if fraction>.001 else Marker.DELETE_MARKER
        marker.type=Marker.SPHERE;marker.pose.position.x=x;marker.pose.position.y=y;marker.pose.position.z=z+1.2;marker.pose.orientation.w=1.
        diameter=data['parachute_diameter_m']*math.sqrt(fraction)
        marker.scale.x=marker.scale.y=max(.001,diameter);marker.scale.z=max(.001,.15*math.sqrt(fraction))
        for color in [marker.material.ambient,marker.material.diffuse]:color.r=1.;color.g=.45;color.b=.05;color.a=.85
        request=Marker_V();request.marker.add().CopyFrom(marker)
        ok,response=self.gz.request('/marker_array',request,Marker_V,Boolean,40)
        if ok and response.data and not self.connected:
            self.connected=True;print('Gazebo canopy illustration connected (visual only)',flush=True)
        if self.follow and not self.follow_started:
            ok,response=self.gz.request('/gui/follow',StringMsg(data='cansat'),StringMsg,Boolean,100)
            if ok and response.data:
                track=CameraTrack();track.track_mode=CameraTrack.FOLLOW;track.follow_target.name='cansat'
                track.follow_offset.x=-2.;track.follow_offset.y=-2.;track.follow_offset.z=1.5
                track.follow_pgain=track.track_pgain=1.
                if self.follow_pub.publish(track):
                    self.follow_started=True;self.camera_ready_at=time.monotonic()+.6
                    print('Gazebo follow camera requested',flush=True)
        if self.follow and (not self.follow_started or time.monotonic()<self.camera_ready_at):return
        stage=flight['stage']
        label='stowed' if stage=='stowed' else ('opening' if stage=='opening' and fraction>.3 else ('open' if stage=='open' else None))
        if label and label not in self.shots:
            folder=self.output/'screenshots'/label;folder.mkdir(parents=True,exist_ok=True)
            ok,response=self.gz.request('/gui/screenshot',StringMsg(data=str(folder)),StringMsg,Boolean,100)
            if ok and response.data:
                self.shots.add(label);(folder/'state.json').write_text(json.dumps(data,indent=2));print('Gazebo screenshot requested: '+label,flush=True)

    def normalize_shots(self):
        for folder in (self.output/'screenshots').glob('*'):
            target=folder/'scene.png'
            if complete_png(target) is not None:continue
            originals=[p for p in folder.glob('*.png') if p.name!='scene.png']
            for original in originals:
                data=complete_png(original)
                if data is None:continue
                # Gazebo queues screenshots before writing them on its render
                # thread. Publish our copy only after the complete PNG exists.
                temporary=folder/'scene.tmp'
                temporary.write_bytes(data);temporary.replace(target)
                break

def complete_png(path):
    try:
        data=path.read_bytes()
        if not data.endswith(b'\x00\x00\x00\x00IEND\xaeB\x60\x82'):return None
        with Image.open(io.BytesIO(data)) as picture:picture.verify()
        return data
    except (OSError,ValueError,SyntaxError):return None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--no-follow',action='store_true');args=parser.parse_args();visual=Visual(args.output,not args.no_follow)
    try:
        while True:
            file=visual.output/'status.json'
            if file.exists():
                try:visual.show(json.loads(file.read_text()))
                except (OSError,ValueError):pass
            visual.normalize_shots();time.sleep(.1)
    except KeyboardInterrupt:pass

if __name__=='__main__':main()
