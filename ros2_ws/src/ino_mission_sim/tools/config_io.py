import argparse,json,tempfile
from pathlib import Path
import yaml
from ground_world import load as load_ground
from mission_config import load_mission
from descent_dynamics import Descent
from shared_camera import ROOT

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['ground','descent']);p.add_argument('path',nargs='?');a=p.parse_args()
    path=Path(a.path) if a.path else ROOT/('config/ground_navigation.yaml' if a.mode=='ground' else 'config/firmware/descent.yaml')
    cfg=load_ground(path) if a.mode=='ground' else load_mission(path)
    if a.mode!='ground':Descent(cfg)
    print(json.dumps(cfg,allow_nan=False))
