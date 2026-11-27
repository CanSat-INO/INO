"""Mission-only YAML inheritance; never reads or writes camera experiment settings."""
from pathlib import Path
from copy import deepcopy
import yaml

def merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result

def load_mission(path, seen=()):
    path = Path(path).resolve()
    if path in seen:
        raise ValueError('Circular mission config inheritance: '+str(path))
    cfg = yaml.safe_load(path.read_text())
    parent = cfg.pop('extends', None)
    return merge(load_mission(path.parent/parent, (*seen, path)), cfg) if parent else cfg
