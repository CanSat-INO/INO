"""Export measured simulation output and actual stopped camera frames."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def report(out):
    out=Path(out);cfg=yaml.safe_load((out/'ground-effective.yaml').read_text())
    (out/'report-provenance.json').write_text(json.dumps(dict(renderer=str(Path(__file__).resolve()),
        renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        trajectory_sha256=hashlib.sha256((out/'trajectory.csv').read_bytes()).hexdigest()),indent=2))
    from review_ground import review
    review(out)
    if not (out/'terrain.npz').exists():return
    data=np.load(out/'terrain.npz');cost=data['cost'];seen=data['seen']
    classes=np.where(~seen,0,np.where(cost>=100,3,np.where(cost>=35,2,1)))
    extent=cfg['map_bounds_m'];extent=[extent[0],extent[2],extent[1],extent[3]]
    fig,axs=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    axs[0].imshow(classes,origin='lower',extent=extent,cmap=ListedColormap(['#41444c','#37b766','#efaa32','#df4747']),vmin=0,vmax=3,interpolation='nearest')
    axs[0].set_title('Stereo-derived traversability + current planned path')
    plans=[]
    if (out/'plans.jsonl').exists():
        plans=[json.loads(line) for line in (out/'plans.jsonl').read_text().splitlines() if line.strip()]
        if plans and plans[-1]['path']:
            p=np.array(plans[-1]['path']);axs[0].plot(p[:,0],p[:,1],color='#ff55dc',linewidth=2,label='Latest plan (unobserved parts provisional)')
    trajectory=np.genfromtxt(out/'trajectory.csv',delimiter=',',names=True,dtype=None,encoding='utf8')
    trajectory=np.atleast_1d(trajectory)
    if len(trajectory):
        for ax in axs:
            ax.plot(trajectory['truth_x'],trajectory['truth_y'],color='#30b9ff',linewidth=1.6,label='Actual path (evaluation only)')
        axs[1].plot(trajectory['estimated_x'],trajectory['estimated_y'],'--',color='#e8a13e',label='SLAM-corrected estimate')
    for ax in axs:
        ax.plot(0,0,'wo',markeredgecolor='black',label='Start')
        ax.plot(*cfg['goal_xy_m'],'*',markersize=14,color='#54dfdc',markeredgecolor='black',label='Goal')
        ax.set(xlim=(extent[0],extent[1]),ylim=(extent[2],extent[3]),xlabel='x [m]',ylabel='y [m]')
        ax.set_aspect('equal');ax.legend(loc='lower right',fontsize=7)
    from matplotlib.patches import Circle,Rectangle
    obstacles=cfg['obstacles']
    cones=list(obstacles['cones'])+([cfg['goal_xy_m']] if cfg.get('goal',{}).get('camera_confirmation') else [])
    for x,y in cones:axs[1].add_patch(Rectangle((x-obstacles['cone_base_m']/2,y-obstacles['cone_base_m']/2),obstacles['cone_base_m'],obstacles['cone_base_m'],color='#e86725'))
    axs[1].add_patch(Circle(cfg['goal_xy_m'],cfg['goal_tolerance_m'],fill=False,edgecolor='#26969c',linestyle=':'))
    for x,y,sx,sy,h in obstacles['boxes']:axs[1].add_patch(Rectangle((x-sx/2,y-sy/2),sx,sy,color='#715536'))
    for name,color in [('ramp','#87ad6f'),('step','#9986b4')]:
        spec=obstacles[name];axs[1].add_patch(Rectangle((spec['center_x_m']-spec['length_m']/2,-spec['width_m']/2),spec['length_m'],spec['width_m'],color=color,alpha=.3,label=name))
    axs[1].set_title('Known course geometry: evaluation view only');axs[1].legend(fontsize=7,loc='lower right')
    result=json.loads((out/'result.json').read_text())
    fig.suptitle(f"Stop and photograph | {result['navigation'].get('photos',0)} mapped photographs | SLAM nodes {result['slam_graph_nodes']}\nGreen: easy / Orange: difficult / Red: blocked / Gray: unknown. Limits are provisional.",fontsize=11)
    fig.savefig(out/'navigation-map.png',dpi=160);plt.close(fig)
    if plans:
        selected=[plans[i] for i in sorted(set(np.linspace(0,len(plans)-1,min(3,len(plans))).astype(int)))]
        fig,axes=plt.subplots(1,len(selected),figsize=(5*len(selected),4.6),squeeze=False,layout='constrained')
        for ax,plan in zip(axes[0],selected):
            ax.imshow(classes,origin='lower',extent=extent,cmap=ListedColormap(['#41444c','#37b766','#efaa32','#df4747']),vmin=0,vmax=3,interpolation='nearest')
            past=trajectory[trajectory['time_s']<=plan['time_s']]
            ax.plot(past['truth_x'],past['truth_y'],color='#30b9ff',linewidth=2,label='Actual path up to this time')
            if plan['path']:
                p=np.array(plan['path']);ax.plot(p[:,0],p[:,1],color='#ff55dc',linewidth=2,label='Saved planned path')
                ax.plot(*p[0],'wo',markeredgecolor='black')
            ax.plot(*cfg['goal_xy_m'],'*',markersize=12,color='#54dfdc',markeredgecolor='black')
            ax.set(xlim=(extent[0],extent[1]),ylim=(extent[2],extent[3]),xlabel='x [m]',ylabel='y [m]',title=f"Plan at simulation t = {plan['time_s']:.1f} s")
            ax.set_aspect('equal');ax.legend(fontsize=7,loc='lower right')
        fig.suptitle('Saved plans overlaid on the FINAL observed terrain\nBackground is not the map available at each earlier time.',fontsize=11)
        fig.savefig(out/'planning-history.png',dpi=160);plt.close(fig)
    frames=sorted(p for p in (out/'photos').glob('*.png') if '-right' not in p.name)
    if frames:
        selected=[frames[i] for i in sorted(set(np.linspace(0,len(frames)-1,min(4,len(frames))).astype(int)))]
        fig,axes=plt.subplots(1,len(selected),figsize=(4*len(selected),3.5),squeeze=False,layout='constrained')
        for ax,file in zip(axes[0],selected):ax.imshow(plt.imread(file));ax.set_title(file.stem,fontsize=9);ax.axis('off')
        fig.suptitle('Actual Gazebo left-camera photographs captured while stopped')
        fig.savefig(out/'stopped-photographs.png',dpi=150);plt.close(fig)
    observations=out/'goal-observations.jsonl'
    if observations.exists():
        detections=[json.loads(line) for line in observations.read_text().splitlines() if line.strip()]
        confirmed=[r for r in detections if r['confirmed'] and r['candidates']]
        if confirmed:
            record=confirmed[-1];fig,ax=plt.subplots(figsize=(8,6),layout='constrained')
            ax.imshow(plt.imread(out/'photos'/record['file']))
            for candidate in record['candidates']:
                u,v=candidate['pixel'];x,y=candidate['map_xy_m'];accepted=candidate['within_coordinate_prior']
                color='#22e696' if accepted else '#e5c15a'
                ax.plot(u,v,'+',markersize=14,mew=2,color=color)
                ax.annotate(f"{'Near goal prior' if accepted else 'Other cone'} ({x:.2f}, {y:.2f}) m",(u,v),xytext=(8,-18),textcoords='offset points',color=color,fontsize=9,bbox=dict(facecolor='black',alpha=.7,edgecolor='none'))
            ax.set_title(f"Stopped camera: coordinate-gated cone confirmation\n{record['file']} | {record['views']} accepted view confirmations")
            ax.axis('off');fig.savefig(out/'goal-confirmation.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('out');report(a.parse_args().out)
