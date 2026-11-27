"""Convert the already-normalized CAD OBJ to binary STL for RViz mesh loading."""
from pathlib import Path
import struct
import numpy as np
from design_config import ROOT

def ensure_stl(shape):
    source=ROOT/'assets/meshes'/f'{shape}.obj'
    target=source.with_suffix('.stl')
    if target.exists() and target.stat().st_mtime>=source.stat().st_mtime:return target
    vertices=[];faces=[]
    for line in source.read_text().splitlines():
        if line.startswith('v '):vertices.append([float(x) for x in line.split()[1:4]])
        elif line.startswith('f '):faces.append([int(x.split('/')[0])-1 for x in line.split()[1:4]])
    xyz=np.array(vertices,np.float32)[np.array(faces)]
    normals=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    data=np.zeros(len(faces),dtype=[('normal','<f4',(3,)),('vertices','<f4',(3,3)),('attribute','<u2')])
    data['normal']=normals;data['vertices']=xyz
    with target.open('wb') as f:
        f.write(f'CanSat {shape}: normalized CAD, metres'.encode().ljust(80,b' '));f.write(struct.pack('<I',len(data)));f.write(data.tobytes())
    return target

if __name__=='__main__':
    for shape in ('deployed','folded'):print(ensure_stl(shape))
