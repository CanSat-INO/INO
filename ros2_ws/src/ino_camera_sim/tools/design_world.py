"""Reproducible camera-design world; synthetic site conditions."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
from scipy.spatial.transform import Rotation
import yaml
from design_config import ROOT,load,rig,geometry_summary
from environment_assets import make_grass,cone_mesh

def mesh(path):
    return f'<geometry><mesh><uri>{Path(path).resolve()}</uri></mesh></geometry>'

def box(size):
    return '<geometry><box><size>'+' '.join(map(str,size))+'</size></box></geometry>'

def visual(name,geometry,color=None,pose='0 0 0 0 0 0'):
    material='' if color is None else f'<material><ambient>{color} 1</ambient><diffuse>{color} 1</diffuse></material>'
    return f'<visual name="{name}"><pose>{pose}</pose>{geometry}{material}</visual>'

def static(name,pose,geometry,color=None,collision=True,collider=None,collision_pose="0 0 0 0 0 0"):
    return f'<model name="{name}"><static>true</static><pose>{pose}</pose><link name="link">'+(f'<collision name="collision"><pose>{collision_pose}</pose>{collider or geometry}</collision>' if collision else '')+visual('visual',geometry,color)+'</link></model>'

def generate(cfg,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'effective.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    (out/'geometry.json').write_text(json.dumps(geometry_summary(cfg),indent=2))
    w=cfg['world'];c=cfg['camera'];r=rig(cfg);rng=random.Random(w['seed'])
    p=['''<sdf version="1.9"><world name="stereo_lab">
<physics name="physics" type="ignored"><max_step_size>.005</max_step_size><real_time_factor>1</real_time_factor></physics>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
<plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
<scene><ambient>.65 .65 .65 1</ambient><background>.65 .75 .85 1</background><shadows>false</shadows></scene>
<light name="sun" type="directional"><pose>0 0 10 0 0 0</pose><diffuse>.8 .8 .8 1</diffuse><direction>-.3 .2 -1</direction></light>
''']
    p.append(static('ground_collision','0 0 -.05 0 0 0',box([w['size_m'],w['size_m'],.1]),'.5 .5 .5'))
    if w['surface']=='lab':
        for i in range(500):
            v=rng.uniform(.05,.95)
            p.append(static(f'patch{i}',f'{rng.uniform(-5,5)} {rng.uniform(-5,5)} .002 0 0 0',box([rng.uniform(.03,.18),rng.uniform(.03,.18),.001]),f'{v} {v*.8} {v*.6}',False))
        for i,(x,y,a,b) in enumerate([(4,0,.3,10),(0,5,8,.3),(0,-5,8,.3)]):
            p.append(static(f'wall{i}',f'{x} {y} 1 0 0 0',box([a,b,2]),'.65 .55 .4'))
            for j in range(70):
                v=rng.random()
                p.append(static(f'mark{i}_{j}',f'{x-a/2-.003} {y+rng.uniform(-b/2,b/2)} {rng.uniform(0,2)} 0 0 0',box([.004,.06,.06]),f'{v} {1-v} .1',False))
    else:
        make_grass(out/'surface',cfg)
        p.append(static('grass_texture','0 0 .001 0 0 0',mesh(out/'surface/ground.dae'),collision=False))
        if w['surface']!='low_texture':p.append(static('grass_blades','0 0 .002 0 0 0',mesh(out/'surface/blades.dae'),collision=False))
    cone_mesh(out/'cone.obj',w['cone_height_m'],w['cone_base_m'])
    for i,(x,y) in enumerate(w['cones']):
        p.append(static(f'cone{i}',f'{x} {y} .03 0 0 0',mesh(out/'cone.dae'),'1 .12 .02',collider=box([w['cone_base_m']*.8,w['cone_base_m']*.8,w['cone_height_m']]),collision_pose=f"0 0 {w['cone_height_m']/2} 0 0 0"))
        p.append(static(f'cone_base{i}',f'{x} {y} .015 0 0 0',box([w['cone_base_m'],w['cone_base_m'],.03]),'.06 .06 .06'))
    for i,(x,y,sx,sy,sz) in enumerate(w['boxes']):p.append(static(f'box{i}',f'{x} {y} {sz/2} 0 0 0',box([sx,sy,sz]),'.4 .3 .15'))
    if w.get('mat_enabled',True):
        mx,my=w['mat_center'];sx,sy=w['mat_size'];h=w['mat_bump_height_m'];spacing=w['mat_bump_spacing_m']
        p.append(static('mat_base',f'{mx} {my} .005 0 0 0',box([sx,sy,.01]),'.15 .25 .25'))
        for ix in range(int(sx/spacing)):
            for iy in range(int(sy/spacing)):
                p.append(static(f'bump{ix}_{iy}',f'{mx-sx/2+(ix+.5)*spacing} {my-sy/2+(iy+.5)*spacing} .01 0 0 0',f'<geometry><sphere><radius>{h}</radius></sphere></geometry>','.2 .35 .35'))
    shape=cfg['robot']['shape'];size=[.215,.272,.171]
    if shape=='simple':body=visual('body',box([.15,.18,.12]),'1 .3 .05','0 0 .09 0 0 0')
    else:
        meta=ROOT/'assets/meshes'/f'{shape}.json'
        if not meta.exists():raise RuntimeError('Run STEP import first: missing '+str(meta))
        model_meta=json.loads(meta.read_text());size=model_meta['size_m']
        model_meta['mesh_sha256']=hashlib.sha256((ROOT/'assets/meshes'/f'{shape}.obj').read_bytes()).hexdigest()
        (out/'model-provenance.json').write_text(json.dumps(model_meta,indent=2))
        body=visual('cad',mesh(ROOT/'assets/meshes'/f'{shape}.obj'))
    p.append(f'''<model name="cansat"><pose>0 0 0 0 0 0</pose><link name="base_link"><gravity>false</gravity><inertial><mass>{cfg['robot']['mass_kg']}</mass><inertia><ixx>.006</ixx><iyy>.008</iyy><izz>.009</izz></inertia></inertial><collision name="body"><pose>0 0 {size[2]/2} 0 0 0</pose>{box(size)}</collision>{body}''')
    for side in ('left','right'):
        xyz=r['positions'][side];angles=Rotation.from_matrix(r['gazebo_rotations'][side]).as_euler('xyz')
        sensor_pose=' '.join(map(str,[*xyz,*angles]))
        p.append(f'''<sensor name="{side}" type="camera"><pose>{sensor_pose}</pose><always_on>true</always_on><update_rate>{c['fps']}</update_rate><topic>/raw/{side}/image</topic><gz_frame_id>{side}_raw_optical</gz_frame_id><camera><horizontal_fov>{math.radians(c['hfov_deg'])}</horizontal_fov><image><width>{c['width']}</width><height>{c['height']}</height><format>R8G8B8</format></image><clip><near>.015</near><far>25</far></clip><camera_info_topic>/raw/{side}/camera_info</camera_info_topic></camera></sensor>''')
        p.append(visual(f'{side}_camera_marker',box([.015,.023,.015]),'.02 .02 .02',sensor_pose))
    p.append('''</link><plugin filename="gz-sim-velocity-control-system" name="gz::sim::systems::VelocityControl"><topic>/cmd_vel</topic></plugin><plugin filename="gz-sim-odometry-publisher-system" name="gz::sim::systems::OdometryPublisher"><dimensions>3</dimensions><odom_publish_frequency>20</odom_publish_frequency><odom_topic>/ground_truth/odom</odom_topic><odom_frame>world</odom_frame><robot_base_frame>truth_base</robot_base_frame></plugin></model></world></sdf>''')
    (out/'world.sdf').write_text('\n'.join(p))
    return out/'world.sdf'

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',default=str(ROOT/'config/design.yaml'));a.add_argument('--out',default=str(ROOT/'worlds/design'));a.add_argument('--set',action='append',default=[]);args=a.parse_args()
    print(generate(load(args.config,args.set),args.out))
