"""Independent release-to-goal SIL launch; stereo.launch.py remains separate."""
import sys,datetime,uuid,shutil,hashlib,json,os
from pathlib import Path
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument,OpaqueFunction,ExecuteProcess,IncludeLaunchDescription,EmitEvent,TimerAction,RegisterEventHandler,SetEnvironmentVariable
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_prefix, get_package_share_directory
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from mission_world import generate
from mission_config import load_mission
from descent_dynamics import Descent

def launch(context):
    get=lambda k:LaunchConfiguration(k).perform(context)
    cfg=load_mission(get('config'))
    cfg['communication']={'ros_domain_id':os.environ.get('ROS_DOMAIN_ID'),'gz_partition':os.environ.get('GZ_PARTITION')}
    if get('profile'):cfg['profile']=get('profile')
    if cfg['profile']=='guarded':cfg.setdefault('sensors',{})
    cfg['keep_open']=(get('gui')=='true') if not get('keep_open') else get('keep_open')=='true'
    if cfg.get('descent'):Descent(cfg)
    if get('duration'):cfg['duration_s']=float(get('duration'))
    if get('controller_executable'):cfg['controller_executable']=get('controller_executable')
    out=Path(get('runtime') or ROOT/'logs'/('mission-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:4]));out.mkdir(parents=True,exist_ok=True)
    middleware_actions=[]
    if cfg.get('middleware')=='zenoh':
        defaults=Path(get_package_share_directory('rmw_zenoh_cpp'))/'config'
        session=out/'zenoh-session.json5';router=out/'zenoh-router.json5'
        session.write_text((defaults/'DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5').read_text().replace('tcp/localhost:7447','tcp/127.0.0.1:17643'))
        router.write_text((defaults/'DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5').read_text().replace('tcp/[::]:7447','tcp/127.0.0.1:17643'))
        cfg['communication'].update(rmw='rmw_zenoh_cpp',zenoh_session_config=str(session))
        middleware_actions=[SetEnvironmentVariable('RMW_IMPLEMENTATION','rmw_zenoh_cpp'),SetEnvironmentVariable('ZENOH_SESSION_CONFIG_URI',str(session)),ExecuteProcess(cmd=[str(Path(get_package_prefix('rmw_zenoh_cpp')) / 'lib/rmw_zenoh_cpp/rmw_zenohd')],additional_env={'ZENOH_ROUTER_CONFIG_URI':str(router)},output='screen')]
    binary=Path(cfg['controller_executable']) if cfg.get('controller_executable') else (ROOT/'firmware/sil/build/stop_controller' if cfg['profile']=='passive' else ROOT/'firmware/sil/build'/cfg['profile']/'legacy_sil')
    shutil.copy2(binary,out/'controller.native')
    manifest={'original_executable':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'platform':'Linux host SIL, not ESP32 firmware'}
    if (binary.parent/'manifest.json').exists():manifest['build']=json.loads((binary.parent/'manifest.json').read_text())
    (out/'controller-manifest.json').write_text(json.dumps(manifest,indent=2))
    cfg['controller_executable']=str((out/'controller.native').resolve())
    source=out/'source';source.mkdir(exist_ok=True)
    for file in ['tools/mission_node.py','tools/mission_world.py','tools/mission_config.py','tools/descent_dynamics.py','tools/descent_visual.py','tools/mission_ready.py','tools/mission_monitor.py','tools/sensor_faults.py','tools/build_legacy_sil.py','launch/mission.launch.py','firmware/sil/arduino_shim.hpp','firmware/sil/sim_port.hpp','firmware/sil/mission_guard.hpp','firmware/sil/stop_controller_example.cpp']:
        shutil.copy2(ROOT/file,source/Path(file).name)
    (out/'mission.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False));world=generate(cfg,out)
    bridge=[dict(ros_topic_name='/clock',gz_topic_name='/clock',ros_type_name='rosgraph_msgs/msg/Clock',gz_type_name='gz.msgs.Clock',direction='GZ_TO_ROS'),dict(ros_topic_name='/mission/plant/cmd_vel',gz_topic_name='/mission/plant/cmd_vel',ros_type_name='geometry_msgs/msg/Twist',gz_type_name='gz.msgs.Twist',direction='ROS_TO_GZ'),dict(ros_topic_name='/ground_truth/odom',gz_topic_name='/ground_truth/odom',ros_type_name='nav_msgs/msg/Odometry',gz_type_name='gz.msgs.Odometry',direction='GZ_TO_ROS')]
    for side in ['left','right']:bridge.append(dict(ros_topic_name=f'/raw/{side}/image',gz_topic_name=f'/raw/{side}/image',ros_type_name='sensor_msgs/msg/Image',gz_type_name='gz.msgs.Image',direction='GZ_TO_ROS'))
    (out/'bridge.yaml').write_text(yaml.safe_dump(bridge))
    nodes=middleware_actions
    bridge_node=Node(package='ros_gz_bridge',executable='parameter_bridge',parameters=[{'config_file':str(out/'bridge.yaml')}],output='screen')
    gz_args=('-r ' if get('gui')=='true' else '-s -r --headless-rendering ')+str(world)
    if get('gui')=='true' and (out/'gui.config').exists():gz_args+=' --gui-config '+str(out/'gui.config')
    nodes.append(IncludeLaunchDescription(PythonLaunchDescriptionSource(str(Path(get_package_share_directory('ros_gz_sim'))/'launch/gz_sim.launch.py')),launch_arguments={'gz_args':gz_args,'on_exit_shutdown':'true'}.items()))
    nodes.append(TimerAction(period=8.,actions=[bridge_node]))
    readiness=ExecuteProcess(cmd=['python3',str(ROOT/'tools/mission_ready.py')],output='screen')
    controller=ExecuteProcess(cmd=['python3',str(ROOT/'tools/mission_node.py'),'--config',str(out/'mission.yaml'),'--output',str(out)],output='screen',on_exit=[EmitEvent(event=Shutdown(reason='Mission completed or stopped'))])
    rviz_node=None
    recorder=None
    if cfg.get('record_bag',False):
        topics=['/clock','/ground_truth/odom','/mission/virtual_sensors','/mission/status','/mission/plant/cmd_vel']
        if cfg.get('record_camera_images',False):topics+=['/raw/left/image','/raw/right/image']
        recorder=ExecuteProcess(cmd=['ros2','bag','record','--use-sim-time','-o',str(out/'rosbag'),'--topics',*topics],output='screen')
    def ready(event,context):
        if event.returncode!=0:return [EmitEvent(event=Shutdown(reason='Virtual sensor startup failed'))]
        actions=[controller]+([rviz_node] if rviz_node else [])
        return [recorder,TimerAction(period=2.,actions=actions)] if recorder else actions
    nodes.append(RegisterEventHandler(OnProcessExit(target_action=readiness,on_exit=ready)))
    nodes.append(TimerAction(period=10.,actions=[readiness]))
    if get('rviz')=='true':
        view=yaml.safe_load((ROOT/'config/mission.rviz').read_text())
        if cfg.get('descent'):view['Visualization Manager']['Views']['Current'].update(Distance=65.,**{'Focal Point':dict(X=15.,Y=0.,Z=15.)})
        (out/'mission.rviz').write_text(yaml.safe_dump(view,sort_keys=False))
        # Initialize Gazebo's sensor renderer before RViz opens its GL context.
        rviz_node=Node(package='rviz2',executable='rviz2',arguments=['-d',str(out/'mission.rviz')],parameters=[{'use_sim_time':True}])
    if get('gui')=='true' and cfg.get('descent'):
        visual_args=[] if cfg['descent'].get('follow_camera',True) else ['--no-follow']
        nodes.append(ExecuteProcess(cmd=['python3',str(ROOT/'tools/descent_visual.py'),'--output',str(out),*visual_args],output='screen'))
    if get('gui')=='true':nodes.append(ExecuteProcess(cmd=['python3',str(ROOT/'tools/mission_monitor.py'),str(out)],output='screen'))
    return nodes
def generate_launch_description():
    defaults=dict(config=str(ROOT/'config/firmware/mission.yaml'),profile='',runtime='',gui='true',rviz='true',keep_open='',duration='',controller_executable='')
    return LaunchDescription([*[DeclareLaunchArgument(k,default_value=v) for k,v in defaults.items()],OpaqueFunction(function=launch)])
