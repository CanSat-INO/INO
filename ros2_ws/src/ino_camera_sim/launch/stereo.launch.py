"""One validated configuration drives rendering, rectification, TF and capture."""
from pathlib import Path
import datetime
import sys
import uuid
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, LogInfo, EmitEvent
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch.events import Shutdown
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from design_config import load,rig
from design_world import generate

def launch_nodes(context):
    get=lambda key:LaunchConfiguration(key).perform(context)
    cfg=load(get('config'))
    if get('capture_mode'):cfg['capture']['mode']=get('capture_mode')
    # Revalidate overrides before creating a world.
    import yaml
    out=Path(get('runtime')) if get('runtime') else ROOT/'logs'/f'manual-{datetime.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}'
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'requested.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    cfg=load(out/'requested.yaml')
    world=generate(cfg,out)
    geometry=rig(cfg)
    sim={'use_sim_time':True}
    gui=get('gui').lower()=='true';slam=get('slam').lower()=='true';rviz=get('rviz').lower()=='true'
    bridge=[]
    for topic,ros_type,gz_type,direction in [('/clock','rosgraph_msgs/msg/Clock','gz.msgs.Clock','GZ_TO_ROS'),('/cmd_vel','geometry_msgs/msg/Twist','gz.msgs.Twist','ROS_TO_GZ'),('/ground_truth/odom','nav_msgs/msg/Odometry','gz.msgs.Odometry','GZ_TO_ROS')]:
        bridge.append(dict(ros_topic_name=topic,gz_topic_name=topic,ros_type_name=ros_type,gz_type_name=gz_type,direction=direction))
    for side in ('left','right'):
        for kind,ros_type,gz_type in [('image','sensor_msgs/msg/Image','gz.msgs.Image'),('camera_info','sensor_msgs/msg/CameraInfo','gz.msgs.CameraInfo')]:
            topic=f'/raw/{side}/{kind}'
            bridge.append(dict(ros_topic_name=topic,gz_topic_name=topic,ros_type_name=ros_type,gz_type_name=gz_type,direction='GZ_TO_ROS'))
    (out/'bridge.yaml').write_text(yaml.safe_dump(bridge))
    nodes=[LogInfo(msg=f'CanSat run directory: {out}'),Node(package='ros_gz_bridge',executable='parameter_bridge',parameters=[{'config_file':str(out/'bridge.yaml')}],output='screen')]
    if gui:
        nodes.append(IncludeLaunchDescription(PythonLaunchDescriptionSource(str(Path(get_package_share_directory('ros_gz_sim'))/'launch/gz_sim.launch.py')),launch_arguments={'gz_args':f'-r {world}','on_exit_shutdown':'true'}.items()))
    else:nodes.append(ExecuteProcess(cmd=['gz','sim','-s','-r',str(world)],output='screen',on_exit=[EmitEvent(event=Shutdown(reason='Gazebo exited'))]))
    for script in ('rectify.py','capture_gate.py'):
        nodes.append(ExecuteProcess(cmd=['python3',str(ROOT/'tools'/script),'--config',str(out/'effective.yaml'),'--ros-args','-p','use_sim_time:=true'],output='screen'))
    for side,index in [('left',1),('right',2)]:
        pos=geometry['positions'][side]
        rect_rot=geometry['raw_rotations'][side]@geometry[f'R{index}'].T
        for frame,rotation in [(f'{side}_optical',rect_rot),(f'{side}_raw_optical',geometry['raw_rotations'][side])]:
            q=Rotation.from_matrix(rotation).as_quat()
            nodes.append(Node(package='tf2_ros',executable='static_transform_publisher',arguments=['--x',str(pos[0]),'--y',str(pos[1]),'--z',str(pos[2]),'--qx',str(q[0]),'--qy',str(q[1]),'--qz',str(q[2]),'--qw',str(q[3]),'--frame-id','base_link','--child-frame-id',frame],parameters=[sim]))
    if slam:
        nodes.append(ExecuteProcess(cmd=['python3',str(ROOT/'tools/slam_display.py'),'--output',str(out/'slam-status.json'),'--config',str(out/'effective.yaml'),'--ros-args','-p','use_sim_time:=true'],output='screen'))
        remaps=[('rgbd_image','/capture/rgbd_image')]
        nodes.append(Node(package='rtabmap_odom',executable='stereo_odometry',parameters=[sim,{'frame_id':'base_link','odom_frame_id':'odom','subscribe_rgbd':True,'approx_sync':False,'qos':1,'Odom/ResetCountdown':'0','Stereo/MaxDisparity':get('stereo_max_disparity')}],remappings=remaps,output='screen'))
        database=get('database') or str(out/'map.db')
        nodes.append(Node(package='rtabmap_slam',executable='rtabmap',parameters=[sim,{'frame_id':'base_link','subscribe_rgbd':True,'subscribe_stereo':False,'subscribe_depth':False,'subscribe_rgb':False,'approx_sync':False,'qos_image':1,'qos_camera_info':1,'database_path':database,'Rtabmap/DetectionRate':'2.0','Grid/Sensor':'1','Grid/RangeMax':'8.0','Stereo/MaxDisparity':get('stereo_max_disparity')}],remappings=remaps,output='screen'))
    if rviz:nodes.append(Node(package='rviz2',executable='rviz2',arguments=['-d',str(ROOT/'config/stereo.rviz')],parameters=[sim]))
    return nodes

def generate_launch_description():
    defaults={'config':str(ROOT/'config/design.yaml'),'capture_mode':'','runtime':'','database':'','gui':'true','slam':'true','rviz':'true','stereo_max_disparity':'128'}
    return LaunchDescription([*[DeclareLaunchArgument(k,default_value=v) for k,v in defaults.items()],OpaqueFunction(function=launch_nodes)])
