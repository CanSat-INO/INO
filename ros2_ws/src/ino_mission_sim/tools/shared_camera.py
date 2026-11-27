"""Reuse camera geometry and CAD without duplicating its models or defaults."""
from pathlib import Path
import importlib.util
import sys
ROOT=Path(__file__).resolve().parents[1]
CAMERA=ROOT.parent/'ino_camera_sim'
if not (CAMERA/'tools/design_config.py').is_file():
    from ament_index_python.packages import get_package_share_directory
    CAMERA=Path(get_package_share_directory('ino_camera_sim'))
sys.path.append(str(CAMERA/'tools'))

def shared(name):
    key='ino_shared_'+name
    if key in sys.modules:return sys.modules[key]
    spec=importlib.util.spec_from_file_location(key,CAMERA/'tools'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[key]=module;spec.loader.exec_module(module)
    if hasattr(module,'ROOT'):module.ROOT=CAMERA
    return module
