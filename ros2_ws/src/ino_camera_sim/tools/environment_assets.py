"""Deterministic, synthetic grass imagery/geometry; not a site reconstruction."""
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from mesh_writer import write_dae

def make_grass(out,cfg):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    w=cfg['world'];rng=np.random.default_rng(w['seed'])
    green=w['surface']=='grass_green';low=w['surface']=='low_texture'
    base=np.array([86,110,48] if green else [143,130,89],float)
    noise=rng.normal(0,1 if low else 13,(2048,2048,1))
    image=Image.fromarray(np.uint8(np.clip(base+noise,0,255)))
    draw=ImageDraw.Draw(image)
    if not low:
        for _ in range(45000):
            x,y=rng.integers(0,2048,2);angle=rng.uniform(0,2*math.pi);length=rng.uniform(3,22)
            color=tuple(np.uint8(np.clip(base+rng.uniform(-45,55),0,255)))
            draw.line((x,y,x+math.cos(angle)*length,y+math.sin(angle)*length),fill=color,width=int(rng.integers(1,3)))
    image.save(out/'grass.png')
    size=w['size_m'];span=w['texture_span_m']
    # OBJ + UVs keeps the ground texture deterministic and independent of Fuel.
    (out/'ground.obj').write_text(f'mtllib ground.mtl\nv {-size/2} {-size/2} 0\nv {size/2} {-size/2} 0\nv {size/2} {size/2} 0\nv {-size/2} {size/2} 0\nvt 0 0\nvt {size/span} 0\nvt {size/span} {size/span}\nvt 0 {size/span}\nusemtl grass\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')
    (out/'ground.mtl').write_text('newmtl grass\nKa .6 .6 .6\nKd 1 1 1\nKs 0 0 0\nmap_Kd grass.png\n')
    write_dae(out/'ground.dae',[[-size/2,-size/2,0],[size/2,-size/2,0],[size/2,size/2,0],[-size/2,size/2,0]],[[0,1,2],[0,2,3]],uv=[[0,0],[size/span,0],[size/span,size/span],[0,size/span]],texture='grass.png')
    if low:return
    verts=[];groups=[[] for _ in range(6)];span=min(size,w['texture_span_m'])
    for i in range(int(w['grass_density'])):
        x,y=rng.uniform(-span/2,span/2,2);h=w['grass_height_m']*rng.uniform(.4,1.4)
        a=rng.uniform(0,math.pi);width=rng.uniform(.001,.004);dx,dy=math.cos(a)*width,math.sin(a)*width
        n=len(verts)+1;verts += [(x-dx,y-dy,0),(x+dx,y+dy,0),(x+dx*.5+h*.15,y+dy*.5,h)]
        groups[i%6].append((n,n+1,n+2))
    with (out/'blades.obj').open('w') as f:
        f.write('mtllib blades.mtl\n')
        for v in verts:f.write('v '+' '.join(f'{t:.6f}' for t in v)+'\n')
        for i,tris in enumerate(groups):
            f.write(f'usemtl blade{i}\n')
            for t in tris:f.write('f '+' '.join(map(str,t))+'\n')
    write_dae(out/'blades.dae',verts,[[v-1 for v in face] for group in groups for face in group],colors=[tuple(np.clip(base/255+(i-2.5)*.035,0,1)) for i in range(6)],groups=[i for i,group in enumerate(groups) for _ in group])
    with (out/'blades.mtl').open('w') as f:
        for i in range(6):
            c=np.clip(base/255+(i-2.5)*.035,0,1)
            f.write(f'newmtl blade{i}\nKd '+' '.join(map(str,c))+'\nKa .5 .5 .5\nKs 0 0 0\n')

def cone_mesh(path,height,base):
    # Rounded traffic-cone appearance, dimensioned as a provisional test object.
    verts=[];faces=[];segments=40
    for z,r in [(.015,base*.4),(height*.92,.025),(height,.012)]:
        for i in range(segments):
            a=i*2*math.pi/segments;verts.append((r*math.cos(a),r*math.sin(a),z))
    for ring in range(2):
        for i in range(segments):
            a=ring*segments+i+1;b=ring*segments+(i+1)%segments+1
            faces += [(a,b,b+segments),(a,b+segments,a+segments)]
    write_dae(Path(path).with_suffix('.dae'),verts,[[v-1 for v in face] for face in faces],colors=[(1.,.12,.02)])
    Path(path).write_text('\n'.join(['v '+' '.join(map(str,v)) for v in verts]+['f '+' '.join(map(str,f)) for f in faces]))
