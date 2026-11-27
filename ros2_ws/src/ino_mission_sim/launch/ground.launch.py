"""Independent, ground-only contact dynamics + stop-camera SLAM navigation."""
from pathlib import Path
import sys
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction, EmitEvent
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ground_world import load, generate
from design_config import load as camera_load, rig


def nodes(context):
    get=lambda key:LaunchConfiguration(key).perform(context)
    cfg=load(get('config'));out=Path(get('runtime')).resolve()
    sensors_only = get('sensors_only') == 'true'
    if sensors_only:
        cfg['virtual_camera_fps'] = float(get('camera_fps'))
        cfg['virtual_imu_hz'] = float(get('imu_hz'))
    world = generate(cfg, out)
    bridge=[]
    topics=[('/clock','rosgraph_msgs/msg/Clock','gz.msgs.Clock','GZ_TO_ROS'),
            ('/cmd_vel','geometry_msgs/msg/Twist','gz.msgs.Twist','ROS_TO_GZ'),
            ('/ground_truth/odom','nav_msgs/msg/Odometry','gz.msgs.Odometry','GZ_TO_ROS'),
            ('/ground/encoder_odom','nav_msgs/msg/Odometry','gz.msgs.Odometry','GZ_TO_ROS'),
            ('/ground/imu','sensor_msgs/msg/Imu','gz.msgs.IMU','GZ_TO_ROS')]
    for side in ('left','right'):
        topics.extend([(f'/raw/{side}/image','sensor_msgs/msg/Image','gz.msgs.Image','GZ_TO_ROS'),
                       (f'/raw/{side}/camera_info','sensor_msgs/msg/CameraInfo','gz.msgs.CameraInfo','GZ_TO_ROS')])
    if sensors_only:
        disabled = set(get('disable').split(','))
        if get('drive') != 'true':
            disabled.add('/cmd_vel')
        routes = yaml.safe_load(get('topics'))
        if not isinstance(routes, dict):
            raise ValueError('topics must map Gazebo topic names to ROS topic names')
        topics = [item for item in topics if item[0] not in disabled]
    else:
        routes = {}
    drive_enabled = sensors_only and any(item[0] == '/cmd_vel' for item in topics)
    for topic, ros, gz, direction in topics:
        ros_topic = '/virtual/internal_drive' if drive_enabled and topic == '/cmd_vel' else routes.get(topic, topic)
        bridge.append(dict(ros_topic_name=ros_topic, gz_topic_name=topic,
                           ros_type_name=ros, gz_type_name=gz, direction=direction))
    (out/'bridge.yaml').write_text(yaml.safe_dump(bridge))
    sim={'use_sim_time':True}
    result=[Node(package='ros_gz_bridge',executable='parameter_bridge',parameters=[{'config_file':str(out/'bridge.yaml')}],output='screen')]
    args=['gz','sim','-r',str(world)]
    if get('gui')!='true':args.insert(2,'-s')
    result.append(ExecuteProcess(cmd=args,output='screen',on_exit=[EmitEvent(event=Shutdown(reason='Gazebo exited'))]))
    pipeline = [('rectify.py',['--config',str(out/'effective.yaml')]),
                         ('ground_capture.py',['--config',str(out/'effective.yaml')]),
                         ('ground_odometry.py',[]),
                         ('ground_navigation.py',['--config',str(out/'ground-effective.yaml'),'--out',str(out)]),
                         ('ground_evaluate.py',['--config',str(out/'ground-effective.yaml'),'--out',str(out)]),
                         ('slam_display.py',['--config',str(out/'effective.yaml'),'--output',str(out/'slam-status.json')])]
    if sensors_only:
        pipeline = [('ground_odometry.py', []), ('virtual_io.py', ['--out', str(out), *(['--drive'] if drive_enabled else [])])]
    for script, extra in pipeline:
        result.append(ExecuteProcess(cmd=['python3',str(ROOT/'tools'/script),*extra,'--ros-args','-p', 'use_sim_time:=true',
            *[arg for src, dst in routes.items() for arg in ('-r', f'{src}:={dst}')]],output='screen',on_exit=[EmitEvent(event=Shutdown(reason='Required ground node exited: '+script))]))
    geometry=rig(camera_load(out/'effective.yaml'))
    for side,index in [('left',1),('right',2)]:
        for frame,rotation in [(f'{side}_optical',geometry['raw_rotations'][side]@geometry[f'R{index}'].T),(f'{side}_raw_optical',geometry['raw_rotations'][side])]:
            pos=geometry['positions'][side];q=Rotation.from_matrix(rotation).as_quat()
            result.append(Node(package='tf2_ros',executable='static_transform_publisher',arguments=['--x',str(pos[0]),'--y',str(pos[1]),'--z',str(pos[2]),'--qx',str(q[0]),'--qy',str(q[1]),'--qz',str(q[2]),'--qw',str(q[3]),'--frame-id','base_link','--child-frame-id',frame],parameters=[sim]))
    if sensors_only:
        if get('bench') != 'none':
            overrides = [item for item in get('bench_set').split(',') if item]
            result.append(ExecuteProcess(cmd=['python3', str(ROOT/'tools/module_bench.py'),
                '--preset', get('bench'), '--log', str(out/'module-events.jsonl'), '--fault', get('bench_fault'),
                *[arg for item in overrides for arg in ('--set', item)]], output='screen',
                on_exit=[EmitEvent(event=Shutdown(reason='Module bench exited'))]))
        return result
    # Intermittent camera observations use uninterrupted *sensor* odometry.
    # Do not run stereo_odometry, whose pose stream disappears while driving.
    result.append(Node(package='rtabmap_slam',executable='rtabmap',parameters=[sim,{
        'frame_id':'base_link','subscribe_rgbd':True,'subscribe_stereo':False,'subscribe_depth':False,
        'subscribe_rgb':False,'approx_sync':True,'approx_sync_max_interval':0.08,'qos_image':1,'qos_camera_info':1,
        'database_path':str(out/'map.db'),'Rtabmap/DetectionRate':'2.0','Grid/Sensor':'1',
        'Grid/RangeMax':'3.0','Grid/CellSize':'0.05','Stereo/MaxDisparity':'128',
        'RGBD/LinearUpdate':'0.04','RGBD/AngularUpdate':'0.05','RGBD/NeighborLinkRefining':'true',
        'Mem/UseOdomGravity':'true','Optimizer/GravitySigma':'0.1','Vis/MinInliers':'12'}],
        remappings=[('rgbd_image','/capture/rgbd_image')],output='screen'))
    if get('rviz')=='true':result.append(Node(package='rviz2',executable='rviz2',arguments=['-d',str(ROOT/'config/ground.rviz')],parameters=[sim]))
    return result


def generate_launch_description():
    defaults={'config':str(ROOT/'config/ground_navigation.yaml'),'runtime':str(ROOT/'logs/ground-manual'),'gui':'true','rviz':'true', 'sensors_only':'false', 'camera_fps':'5',
              'imu_hz':'50', 'disable':'', 'topics':'{}', 'drive':'false', 'bench':'none', 'bench_set':'', 'bench_fault':'none'}
    return LaunchDescription([*[DeclareLaunchArgument(k,default_value=v) for k,v in defaults.items()],OpaqueFunction(function=nodes)])
