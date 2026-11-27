"""Separate mission world; reuse visuals without modifying camera experiments."""
from pathlib import Path
import xml.etree.ElementTree as ET
from design_world import generate as camera_world
from design_config import ROOT,load

def generate(mission,out):
    cfg=load(ROOT/'config/firmware/mission_scene.yaml');cfg['capture']['mode']='continuous'
    cfg['world'].update(size_m=mission.get('world_size_m',30.),cones=[mission['goal_xy_m']],boxes=[],mat_enabled=False)
    cfg['robot']['shape']='deployed'
    file=camera_world(cfg,out)
    tree=ET.parse(file);world=tree.getroot().find('world');world.set('name','mission_lab')
    model=world.find("model[@name='cansat']")
    import math
    model.find('pose').text=f"0 0 {mission['release_height_m']} 0 0 {math.radians(mission.get('release_yaw_deg',0.))}"
    if mission.get('descent'):
        default_gui=Path.home()/'.gz/sim/8/gui.config'
        if default_gui.exists():
            # Gazebo's GUI config is an XML fragment with multiple root nodes.
            text=default_gui.read_text();text=text.replace('<?xml version="1.0"?>','')
            gui=ET.fromstring('<config>'+text+'</config>')
            scene=gui.find(".//plugin[@filename='MinimalScene']")
            if scene is not None:
                pose=scene.find('camera_pose')
                if pose is None:pose=ET.SubElement(scene,'camera_pose')
                pose.text='-30 -40 45 0 0.46 0.73'
                if mission['descent'].get('follow_camera',True):
                    pose.text=f"-3 -3 {mission['release_height_m']+2} 0 0.44 0.7854"
                    tracking=gui.find(".//plugin[@filename='CameraTracking']")
                    if tracking is None:tracking=ET.SubElement(gui,'plugin',filename='CameraTracking',name='Camera tracking')
                    for name,value in [('follow_target','cansat'),('follow_offset','-3 -3 2'),('follow_pgain','0.2')]:
                        field=tracking.find(name)
                        if field is None:field=ET.SubElement(tracking,name)
                        field.text=value
                if gui.find(".//plugin[@filename='Screenshot']") is None:ET.SubElement(gui,'plugin',filename='Screenshot',name='Screenshot')
                (Path(out)/'gui.config').write_text('\n'.join(ET.tostring(child,encoding='unicode') for child in gui))
    for plugin in model.findall('plugin'):
        if 'VelocityControl' in plugin.get('name',''):plugin.find('topic').text='/mission/plant/cmd_vel'
    tree.write(file,encoding='unicode')
    return file
