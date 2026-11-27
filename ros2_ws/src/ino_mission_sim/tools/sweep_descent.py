"""Standalone scientific figures and reproducible deterministic scenario grid.

No statistical confidence interval or real-world optimum is inferred. Acceptance
is an explicit numerical filter over the full descent, not terminal speed alone.
"""
import argparse,csv,hashlib,itertools,json,math,shutil
from copy import deepcopy
from pathlib import Path
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from compare_descent import simulate
from mission_config import load_mission

ROOT=Path(__file__).resolve().parents[1]
COLORS=['#286090','#b78020','#9b4b76']

def evaluate_grid(base,grid):
    for key in ['diameter_m','trigger_time_s','opening_s','wind_mps']:
        if not grid[key] or any(not math.isfinite(x) or x<0 or (key=='diameter_m' and x==0) for x in grid[key]):raise ValueError('Invalid grid: '+key)
    rows=[]
    for diameter,trigger,opening,wind in itertools.product(grid['diameter_m'],grid['trigger_time_s'],grid['opening_s'],grid['wind_mps']):
        cfg=deepcopy(base);cfg['parachute_diameter_m']=diameter;cfg['descent']['wind'].update(mean_enu_mps=[wind,0.,0.],gusts=[],turbulence_std_mps=0.)
        cfg['descent']['parachute'].update(trigger='time',trigger_time_s=trigger,delay_s=0.,opening_s=opening,failure=False,max_fraction=1.)
        data,metrics=simulate(cfg);rows.append(dict(diameter_m=diameter,trigger_s=trigger,opening_s=opening,wind_mps=wind,landed=bool(data[-1,3]<=1e-6),**metrics))
    candidates=[]
    for diameter,trigger,opening in itertools.product(grid['diameter_m'],grid['trigger_time_s'],grid['opening_s']):
        selected=[r for r in rows if (r['diameter_m'],r['trigger_s'],r['opening_s'])==(diameter,trigger,opening)]
        peak=max(r['peak_descent_mps'] for r in selected);drift=max(r['drift_m'] for r in selected)
        candidates.append(dict(diameter_m=diameter,trigger_s=trigger,opening_s=opening,worst_peak_mps=peak,worst_drift_m=drift,passes_filter=all(r['landed'] for r in selected) and peak<=grid['max_vertical_speed_mps']))
    candidates.sort(key=lambda c:(not c['passes_filter'],c['worst_drift_m'],c['worst_peak_mps']))
    return rows,candidates

def write_csv(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)

def figures(out,rows,candidates,base,grid):
    plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(13,10),layout='constrained')
    ref_d=min(grid['diameter_m'],key=lambda d:abs(d-.76));ref_w=min(grid['wind_mps'],key=lambda w:abs(w-6.))
    ax=axes[0,0]
    for diameter,color,marker in zip(grid['diameter_m'],itertools.cycle(COLORS),itertools.cycle(['o','s','^'])):
        data=[r for r in rows if r['diameter_m']==diameter and r['wind_mps']==ref_w]
        ax.scatter([r['drift_m'] for r in data],[r['peak_descent_mps'] for r in data],c=color,marker=marker,s=35,label=f'Diameter {diameter:.2f} m')
    ax.axhline(grid['max_vertical_speed_mps'],color='#444444',ls='--',label=f"{grid['max_vertical_speed_mps']:g} m/s comparison threshold")
    ax.set(xlabel='Drift at ground contact [m]',ylabel='Maximum downward speed [m/s]',title=f'Wind {ref_w:g} m/s: speed and drift tradeoff');ax.legend(fontsize=9)
    ax=axes[0,1];matrix=[]
    for opening in grid['opening_s']:
        matrix.append([next(r['peak_descent_mps'] for r in rows if (r['diameter_m'],r['wind_mps'],r['trigger_s'],r['opening_s'])==(ref_d,ref_w,trigger,opening)) for trigger in grid['trigger_time_s']])
    im=ax.imshow(matrix,cmap='Blues',origin='lower',aspect='auto',vmin=0)
    ax.set(xticks=range(len(grid['trigger_time_s'])),xticklabels=grid['trigger_time_s'],yticks=range(len(grid['opening_s'])),yticklabels=grid['opening_s'],xlabel='Opening trigger after release [s]',ylabel='Area ramp duration [s]',title=f'Diameter {ref_d:g} m, wind {ref_w:g} m/s: peak speed')
    for i,row in enumerate(matrix):
        for j,value in enumerate(row):ax.text(j,i,f'{value:.1f}',ha='center',va='center',color='white' if value>np.max(matrix)*.6 else '#202020')
    fig.colorbar(im,ax=ax,label='Maximum downward speed [m/s]')
    examples=[('Current: wait 1.0 s / ramp 1.5 s',1.,1.5),('Early: wait 0.1 s / ramp 0.3 s',.1,.3),('Late: wait 2.0 s / ramp 1.5 s',2.,1.5)]
    for (label,trigger,opening),color in zip(examples,COLORS):
        trigger=min(grid['trigger_time_s'],key=lambda t:abs(t-trigger));opening=min(grid['opening_s'],key=lambda t:abs(t-opening));label=f'Wait {trigger:g} s / ramp {opening:g} s'
        cfg=deepcopy(base);cfg['parachute_diameter_m']=ref_d;cfg['descent']['wind']['mean_enu_mps']=[ref_w,0.,0.];cfg['descent']['parachute'].update(trigger_time_s=trigger,opening_s=opening)
        d,m=simulate(cfg);axes[1,0].plot(d[:,0],-d[:,6],color=color,label=label)
        selected=[r for r in rows if (r['diameter_m'],r['trigger_s'],r['opening_s'])==(ref_d,trigger,opening)]
        selected.sort(key=lambda r:r['wind_mps']);axes[1,1].plot([r['wind_mps'] for r in selected],[r['drift_m'] for r in selected],color=color,marker='o',label=label)
    axes[1,0].axhline(grid['max_vertical_speed_mps'],color='#444444',ls='--');axes[1,0].set(xlabel='Time after release [s]',ylabel='Downward speed [m/s]',title=f'Opening transient, diameter {ref_d:g} m, wind {ref_w:g} m/s')
    axes[1,1].set(xlabel='Constant wind [m/s]',ylabel='Drift at ground contact [m]',title='Earlier opening increases exposure to wind')
    for ax in [axes[1,0],axes[1,1]]:ax.legend(fontsize=8)
    for ax in [axes[0,0],axes[1,0],axes[1,1]]:ax.grid(alpha=.2)
    fig.suptitle(f"NUMERICAL SCENARIOS ONLY: {len(rows)} combinations, release {base['release_height_m']:g} m\nMass {base['mass_kg']:g} kg, nominal Cd {base['drag_coefficient']:g}; no attitude, cloth, impact, or field calibration",fontsize=13)
    fig.savefig(out/'sweep-summary.png',dpi=145);plt.close(fig)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(ROOT/'logs/descent-design-sweep'));args=parser.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    base=load_mission(ROOT/'config/firmware/descent.yaml');grid=yaml.safe_load((ROOT/'config/firmware/descent_sweep.yaml').read_text())
    rows,candidates=evaluate_grid(base,grid);write_csv(out/'cases.csv',rows);write_csv(out/'candidates.csv',candidates)
    chosen=next((c for c in candidates if c['passes_filter']),None);sensitivity=[]
    if chosen:
        for factor in grid['cd_sensitivity_factors']:
            cfg=deepcopy(base);cfg['parachute_diameter_m']=chosen['diameter_m'];cfg['drag_coefficient']*=factor
            cfg['descent']['parachute'].update(trigger_time_s=chosen['trigger_s'],opening_s=chosen['opening_s'])
            _,metrics=simulate(cfg);sensitivity.append(dict(cd_factor=factor,cd=cfg['drag_coefficient'],wind_mps=cfg['descent']['wind']['mean_enu_mps'][0],**metrics))
        write_csv(out/'cd-sensitivity.csv',sensitivity)
    manifest=dict(evidence='deterministic point-mass numerical scenarios, not Gazebo runs or measured uncertainty',base=base,grid=grid,case_count=len(rows),candidate_count=len(candidates),filter='all tested winds landed and peak downward speed <= threshold',ranking='among passing candidates, minimize largest drift over tested winds; diameter/packaging not optimized',selected=chosen,cd_sensitivity=sensitivity,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['tools/descent_dynamics.py','tools/compare_descent.py','tools/sweep_descent.py']})
    source=out/'source';source.mkdir(exist_ok=True)
    for name in manifest['source_sha256']:shutil.copy2(ROOT/name,source/Path(name).name)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2));figures(out,rows,candidates,base,grid)
    print(json.dumps({k:manifest[k] for k in ['case_count','selected','cd_sensitivity']},indent=2))

if __name__=='__main__':main()
