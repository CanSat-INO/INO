"""Validate JSON/YAML camera configuration using the simulation's own validator."""
import argparse
import json
from design_config import load

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('path',nargs='?')
    args=parser.parse_args()
    print(json.dumps(load(args.path),ensure_ascii=False,allow_nan=False))
