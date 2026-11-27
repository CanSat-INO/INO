"""Small COLLADA writer with explicit normals, UVs and material bindings."""
from pathlib import Path
import numpy as np

def write_dae(path,vertices,faces,colors=None,uv=None,texture=None,groups=None):
    path=Path(path);v=np.asarray(vertices,float);f=np.asarray(faces,int)
    normals=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    colors=colors or [(.6,.6,.6)]
    groups=np.asarray(groups if groups is not None else np.zeros(len(f),int))
    lines=['<?xml version="1.0" encoding="utf-8"?>','<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1"><asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>']
    if texture:lines.append(f'<library_images><image id="tex"><init_from>{texture}</init_from></image></library_images>')
    lines.append('<library_effects>')
    for i,color in enumerate(colors):
        image='<newparam sid="surface"><surface type="2D"><init_from>tex</init_from></surface></newparam><newparam sid="sampler"><sampler2D><source>surface</source><wrap_s>WRAP</wrap_s><wrap_t>WRAP</wrap_t></sampler2D></newparam>' if texture else ''
        diffuse='<texture texture="sampler" texcoord="UVMap"/>' if texture else '<color>'+' '.join(map(str,(*color,1)))+'</color>'
        lines.append(f'<effect id="effect{i}"><profile_COMMON>{image}<technique sid="common"><phong><emission><color>0 0 0 1</color></emission><ambient><color>.3 .3 .3 1</color></ambient><diffuse>{diffuse}</diffuse><specular><color>0 0 0 1</color></specular><shininess><float>1</float></shininess></phong></technique></profile_COMMON></effect>')
    lines.append('</library_effects><library_materials>')
    for i in range(len(colors)):lines.append(f'<material id="material{i}"><instance_effect url="#effect{i}"/></material>')
    lines.append('</library_materials><library_geometries><geometry id="mesh"><mesh>')
    for name,values,params in [('pos',v,'X Y Z'),('normal',normals,'X Y Z')]+([('uv',np.asarray(uv),'S T')] if uv is not None else []):
        stride=len(params.split());flat=' '.join(f'{x:.7g}' for x in values.ravel())
        lines.append(f'<source id="{name}"><float_array id="{name}-array" count="{values.size}">{flat}</float_array><technique_common><accessor source="#{name}-array" count="{len(values)}" stride="{stride}">'+''.join(f'<param name="{p}" type="float"/>' for p in params.split())+'</accessor></technique_common></source>')
    lines.append('<vertices id="vertices"><input semantic="POSITION" source="#pos"/></vertices>')
    for i in range(len(colors)):
        ids=np.flatnonzero(groups==i)
        data=[]
        for j in ids:
            for vertex in f[j]:data.extend([int(vertex),int(j)]+([int(vertex)] if uv is not None else []))
        lines.append(f'<triangles material="slot{i}" count="{len(ids)}"><input semantic="VERTEX" source="#vertices" offset="0"/><input semantic="NORMAL" source="#normal" offset="1"/>'+('<input semantic="TEXCOORD" source="#uv" offset="2" set="0"/>' if uv is not None else '')+'<p>'+' '.join(map(str,data))+'</p></triangles>')
    lines.append('</mesh></geometry></library_geometries><library_visual_scenes><visual_scene id="scene"><node id="node"><instance_geometry url="#mesh"><bind_material><technique_common>')
    for i in range(len(colors)):lines.append(f'<instance_material symbol="slot{i}" target="#material{i}"><bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/></instance_material>')
    lines.append('</technique_common></bind_material></instance_geometry></node></visual_scene></library_visual_scenes><scene><instance_visual_scene url="#scene"/></scene></COLLADA>')
    path.write_text('\n'.join(lines))
