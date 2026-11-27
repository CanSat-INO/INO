"""Independent ground world: contact-driven tracks and actual stereo cameras.

CAD is visual only. Contact geometry, mass distribution and friction are assumed.
No base VelocityControl, pose teleportation or ground-height lookup is used.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import random
import xml.etree.ElementTree as ET
import yaml
from design_config import ROOT, load as load_camera
from design_world import generate as generate_camera, static, box, visual, mesh


def load(path=None):
    path = Path(path or ROOT/'config/ground_navigation.yaml').resolve()
    cfg = yaml.safe_load(path.read_text())
    for name in ('speed_mps', 'turn_rate_radps', 'goal_tolerance_m', 'resolution_m',
                 'footprint_radius_m', 'max_step_m', 'max_slope_deg', 'max_sensor_age_s', 'duration_s'):
        if not math.isfinite(cfg[name]) or cfg[name] <= 0:
            raise ValueError('Invalid '+name)
    if cfg['speed_mps'] > .2 or cfg['turn_rate_radps'] > .5:
        raise ValueError('Ground mode is limited to slow exploratory driving')
    for name in ('drive_step_m','turn_step_deg','settle_s','capture_period_s','max_observation_range_m','safety_margin_m','max_roughness_m'):
        if not math.isfinite(cfg[name]) or cfg[name]<=0:raise ValueError('Invalid '+name)
    if cfg['drive_step_m']>.2 or cfg['turn_step_deg']>30 or cfg['max_slope_deg']>=60:
        raise ValueError('Unreasonable step / turn / slope setting')
    for key in ('mass_kg','track_length_m','track_width_m','track_height_m','track_separation_m','friction'):
        if not math.isfinite(cfg['robot'][key]) or cfg['robot'][key]<=0:raise ValueError('Invalid robot '+key)
    for name in ('ramp','step'):
        spec=cfg['obstacles'][name]
        for key in ('length_m','width_m','height_m'):
            if not math.isfinite(spec[key]) or spec[key]<=0:raise ValueError('Invalid '+name+' '+key)
    cfg.setdefault('goal',dict(camera_confirmation=False,association_radius_m=.6,confirmation_views=2,stop_margin_m=.03,cone_base_height_m=.03))
    cfg['goal'].setdefault('cone_visible_radius_ratio',.4)
    for key in ('association_radius_m','stop_margin_m','cone_base_height_m','cone_visible_radius_ratio'):
        if not math.isfinite(cfg['goal'][key]) or cfg['goal'][key]<=0:raise ValueError('Invalid goal '+key)
    if cfg['goal']['confirmation_views']<2:raise ValueError('Goal confirmation needs at least two views')
    if cfg['goal']['camera_confirmation'] and cfg['goal_tolerance_m']-cfg['goal']['stop_margin_m']<=cfg['footprint_radius_m']+cfg['obstacles']['cone_base_m']/2+cfg['safety_margin_m']:
        raise ValueError('Goal tolerance must leave room for the robot, cone base and safety margin')
    x0,y0,x1,y1 = cfg['map_bounds_m']
    if not (x0 < 0 < x1 and y0 < 0 < y1 and x0 < cfg['goal_xy_m'][0] < x1
            and y0 < cfg['goal_xy_m'][1] < y1):
        raise ValueError('Start and goal must be inside map bounds')
    if max((x1-x0), (y1-y0))/cfg['resolution_m'] > 500:
        raise ValueError('Too many grid cells')
    cfg['camera_config'] = str((ROOT/cfg['camera_config']).resolve())
    return cfg


def element(parent, tag, text=None, **attrs):
    item = ET.SubElement(parent, tag, attrs)
    if text is not None:
        item.text = str(text)
    return item


def ramp_mesh(path, length, width, height):
    # Closed, triangular prism. Texture-like marks are independent visuals below.
    vertices = [(-length/2,-width/2,0), (length/2,-width/2,0), (0,-width/2,height),
                (-length/2,width/2,0), (length/2,width/2,0), (0,width/2,height)]
    faces = [(1,3,2),(4,5,6),(1,2,5),(1,5,4),(2,3,6),(2,6,5),(3,1,4),(3,4,6)]
    path.write_text('\n'.join(['v '+' '.join(map(str,v)) for v in vertices]
                              +['f '+' '.join(map(str,f)) for f in faces]))


def generate(cfg, out):
    out = Path(out).resolve(); out.mkdir(parents=True, exist_ok=True)
    scene = load_camera(cfg['camera_config'])
    # Ground mode needs 2 Hz stopped pairs, not the comparison mode's 10 Hz.
    scene['camera']['fps'] = cfg.get('virtual_camera_fps', 5.)
    imu_hz = cfg.get('virtual_imu_hz', 50.)
    if not 0 < scene['camera']['fps'] <= 60 or not 0 < imu_hz <= 200:
        raise ValueError('Camera rate must be 0–60 Hz and IMU rate 0–200 Hz (exclusive of zero)')
    scene['capture'].update(mode='stop', settle_s=cfg['settle_s'], period_s=cfg['capture_period_s'], skew_s=0., jpeg_quality=100,
                            acquisition_s=0., transmission_s=0., drop_probability=0.)
    cones=copy.deepcopy(cfg['obstacles']['cones'])
    if cfg['goal']['camera_confirmation']:cones.append(cfg['goal_xy_m'])
    scene['world'].update(size_m=10., texture_span_m=8., surface='grass_dry', seed=cfg['seed'],
                          grass_density=16000, cones=cones,
                          cone_height_m=cfg['obstacles']['cone_height_m'],
                          cone_base_m=cfg['obstacles']['cone_base_m'],
                          boxes=cfg['obstacles']['boxes'], mat_enabled=False)
    scene['robot'].update(shape='deployed', mass_kg=cfg['robot']['mass_kg'])
    file = generate_camera(scene,out)
    tree = ET.parse(file); world = tree.getroot().find('world'); world.set('name','ground_navigation')
    world.find('physics/max_step_size').text = '.002'
    model = world.find("model[@name='cansat']")
    # Evaluation only: align truth samples with 50 Hz IMU and 5 Hz images.
    model.find("plugin[@name='gz::sim::systems::OdometryPublisher']/odom_publish_frequency").text='100'
    model.find('pose').text = '0 0 .004 0 0 0'
    body = model.find("link[@name='base_link']")
    body.find('gravity').text='true'
    element(world,'plugin',filename='gz-sim-imu-system',name='gz::sim::systems::Imu')
    imu=element(body,'sensor',name='ground_imu',type='imu')
    element(imu,'always_on','true');element(imu,'update_rate',imu_hz);element(imu,'topic','/ground/imu')
    element(imu,'gz_frame_id','base_link');element(imu,'imu')
    body.find('inertial/mass').text=str(cfg['robot']['mass_kg']*.7)
    element(body.find('inertial'), 'pose', '0 0 .09 0 0 0')
    old = body.find('collision'); body.remove(old)
    body.append(ET.fromstring('<collision name="body"><pose>0 0 .105 0 0 0</pose>'+box([.15,.17,.09])+'</collision>'))
    for plugin in list(model.findall('plugin')):
        if 'VelocityControl' in plugin.get('name',''):
            model.remove(plugin)
    r=cfg['robot']; length=r['track_length_m']; height=r['track_height_m']; width=r['track_width_m']
    for side, sign in [('left',1),('right',-1)]:
        link=element(model,'link',name=side+'_track')
        element(link,'pose',f"0 {sign*r['track_separation_m']/2} {height/2} 0 0 0")
        element(link,'gravity','true')
        inertia=element(link,'inertial'); element(inertia,'mass',r['mass_kg']*.15)
        tensor=element(inertia,'inertia')
        for axis,value in [('ixx',.00005),('iyy',.0005),('izz',.0005)]:element(tensor,axis,value)
        # Rounded ends let a rigid contact belt engage small edges.
        geometries=[('belt',box([length-height,width,height]),'0 0 0 0 0 0')]
        for front,sign_x in [('front',1),('rear',-1)]:
            geometries.append((front,f'<geometry><cylinder><radius>{height/2}</radius><length>{width}</length></cylinder></geometry>',
                               f'{sign_x*(length-height)/2} 0 0 {math.pi/2} 0 0'))
        for name,geometry,pose in geometries:
            collision=ET.fromstring(f'<collision name="{name}"><pose>{pose}</pose>{geometry}<surface><friction><ode><mu>{r["friction"]}</mu><mu2>{r["friction"]}</mu2></ode></friction></surface></collision>')
            link.append(collision)
        joint=element(model,'joint',name=side+'_track_fixed',type='fixed')
        element(joint,'parent','base_link');element(joint,'child',side+'_track')
        plugin=element(model,'plugin',filename='gz-sim-track-controller-system',name='gz::sim::systems::TrackController')
        element(plugin,'link',side+'_track');element(plugin,'max_command_age','.4')
        element(plugin,'min_velocity','-.2');element(plugin,'max_velocity','.2')
    plugin=element(model,'plugin',filename='gz-sim-tracked-vehicle-system',name='gz::sim::systems::TrackedVehicle')
    for side in ('left','right'):element(element(plugin,side+'_track'),'link',side+'_track')
    element(plugin,'tracks_separation',r['track_separation_m']);element(plugin,'track_height',height)
    element(plugin,'steering_efficiency','1');element(plugin,'topic','/cmd_vel')
    element(plugin,'odom_topic','/ground/encoder_odom');element(plugin,'frame_id','encoder_odom')
    element(plugin,'child_frame_id','encoder_base');element(plugin,'odom_publish_frequency','20')
    for name,tag in [('ramp','ramp'),('step','step')]:
        spec=cfg['obstacles'][name]; x=spec['center_x_m'];sx=spec['length_m'];sy=spec['width_m'];h=spec['height_m']
        if name=='ramp':
            path=out/'ramp.obj';ramp_mesh(path,sx,sy,h);geometry=mesh(path);z=0.
        else:geometry=box([sx,sy,h]);z=h/2
        obstacle=ET.fromstring(static(name,f'{x} 0 {z} 0 0 0',geometry,'.36 .38 .25'))
        if name=='ramp':
            # DART/ODE can crash on imported meshes without vertex normals.
            # Use two primitive, inclined contact surfaces; mesh is visual only.
            link=obstacle.find('link');link.remove(link.find('collision'))
            angle=math.atan2(h,sx/2);thickness=.02
            for side,sign in [('entry',-1),('exit',1)]:
                center_x=sign*sx/4-sign*thickness/2*math.sin(angle)
                center_z=h/2-thickness/2*math.cos(angle)
                link.append(ET.fromstring(f'<collision name="{side}"><pose>{center_x} 0 {center_z} 0 {sign*angle} 0</pose>'+box([math.hypot(sx/2,h),sy,thickness])+'</collision>'))
        world.append(obstacle)
        # Fine visible patches produce stereo features on the raised surfaces.
        rng=random.Random(cfg['seed']+len(tag))
        for i in range(180):
            dx=rng.uniform(-sx/2+.008,sx/2-.008);y=rng.uniform(-sy/2,sy/2)
            top=h*(1-abs(dx)/(sx/2)) if name=='ramp' else h
            v=rng.uniform(.15,.65)
            world.append(ET.fromstring(static(f'{name}_mark_{i}',f'{x+dx} {y} {top+.0005} 0 0 0',
                                               box([.012,.025,.0003]),f'{v} {v*.85} {v*.5}',False)))
    if not cfg['goal']['camera_confirmation']:
        goal=cfg['goal_xy_m']
        world.append(ET.fromstring(static('goal_marker',f'{goal[0]} {goal[1]} .002 0 0 0',box([.35,.35,.002]),'.15 .65 .2',False)))
    tree.write(file,encoding='unicode')
    (out/'ground-effective.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    (out/'ground-model.json').write_text(json.dumps(dict(model='Gazebo TrackController contact-surface velocity',
        calibrated=False, caveats=['rigid contact belts, approximate contact geometry', 'no FIT0522 torque/current/encoder calibration',
        'static synthetic grass; no vegetation deformation'],truth_for_control=False),indent=2))
    return file


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config');a.add_argument('--out',required=True);args=a.parse_args()
    print(generate(load(args.config),args.out))
