"""Reproducible model comparison; optional separate, real Gazebo integrations."""
import argparse,csv,datetime,json,os,subprocess
from copy import deepcopy
from pathlib import Path
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from descent_dynamics import Descent
from mission_config import load_mission

ROOT=Path(__file__).resolve().parents[1]

def cases():
    base=load_mission(ROOT/'config/firmware/descent.yaml');result={}
    for name,speed in [('calm',0.),('wind3',3.),('wind6',6.),('wind7p5',7.5)]:
        cfg=deepcopy(base);cfg['descent']['wind']['mean_enu_mps']=[speed,0.,0.];result[name]=cfg
    result['gust']=load_mission(ROOT/'config/firmware/descent_gust.yaml')
    cfg=deepcopy(base);cfg['release_yaw_deg']=90.;result['wind6_yaw90']=cfg
    for name,trigger,opening,fraction,failed in [('quick_open',.1,.3,1.,False),('late_open',3.,1.5,1.,False),('partial',1.,1.5,.5,False),('failed',1.,1.5,1.,True)]:
        cfg=deepcopy(base);cfg['descent']['parachute'].update(trigger_time_s=trigger,opening_s=opening,max_fraction=fraction,failure=failed);result[name]=cfg
    return result

def simulate(cfg):
    flight=Descent(cfg);pos=np.array([0.,0.,cfg['release_height_m']]);rows=[];dt=.005;t=0.;peak=0.
    while pos[2]>0 and t<cfg['duration_s']:
        info=flight.info(t);rows.append([t,*pos,*flight.velocity,*info['wind_enu_mps'],flight.fraction,info['cda_m2'],0])
        old=pos.copy();velocity,_=flight.advance(t+dt,dt,pos[2]);pos+=velocity*dt;t+=dt;peak=max(peak,-velocity[2])
        if pos[2]<=0:
            # Interpolate the crossing, preserving pre-contact velocity separately.
            fraction=old[2]/max(1e-12,old[2]-pos[2]);pos=old+fraction*(pos-old);t-=dt*(1-fraction)
    rows.append([t,*pos,*flight.velocity,*flight.wind(t),flight.fraction,flight.body_cda+flight.full_cda*flight.fraction,int(pos[2]<=0)])
    return np.array(rows),dict(flight_time_s=float(t),drift_m=float(np.linalg.norm(pos[:2])),landing_x_m=float(pos[0]),landing_y_m=float(pos[1]),precontact_vertical_mps=abs(float(flight.velocity[2])),peak_descent_mps=float(peak),open_fraction=float(flight.fraction))

def plot(runs,path,label):
    fig,axes=plt.subplots(2,2,figsize=(12,9))
    for name,d in runs.items():
        axes[0,0].plot(d[:,0],d[:,3],label=name)
        axes[0,1].plot(d[:,1],d[:,3],label=name)
        axes[1,0].plot(d[:,0],-d[:,6],label=name)
        axes[1,1].plot(d[:,0],100*d[:,10],label=name)
    axes[0,0].set(xlabel='Time since release [s]',ylabel='Height [m]',title='Free fall and staged opening')
    axes[0,1].set(xlabel='East drift [m]',ylabel='Height [m]',title='Wind-driven displacement')
    axes[1,0].set(xlabel='Time since release [s]',ylabel='Downward model velocity [m/s]',title='Includes opening transient')
    axes[1,0].axhline(5,color='red',linestyle='--',label='5 m/s reference')
    axes[1,1].set(xlabel='Time since release [s]',ylabel='Effective canopy area [%]',title='Not fabric shape or inflation pressure')
    for ax in axes.flat:ax.grid(alpha=.3);ax.legend(fontsize=8)
    fig.suptitle(label+'\n30m / assumed CdA, no attitude or cloth model',fontsize=12);fig.tight_layout();fig.savefig(path,dpi=140);plt.close(fig)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out');parser.add_argument('--gazebo',action='store_true');parser.add_argument('--reuse',action='store_true');parser.add_argument('--cases',nargs='+');a=parser.parse_args()
    out=Path(a.out or ROOT/'logs'/('descent-comparison-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))).resolve();out.mkdir(parents=True,exist_ok=True)
    selected=cases();selected={name:selected[name] for name in a.cases} if a.cases else selected
    if not a.gazebo and not a.cases:selected.pop('wind6_yaw90')
    runs={};summary=[];gz_runs={};checks={}
    header=['time_s','x','y','z','model_vx','model_vy','model_vz','wind_e','wind_n','wind_u','open_fraction','cda_m2','grounded']
    for name,cfg in selected.items():
        folder=out/name;folder.mkdir(exist_ok=True);(folder/'input.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
        data,metrics=simulate(cfg);runs[name]=data;summary.append(dict(case=name,**metrics))
        np.savetxt(folder/'model.csv',data,delimiter=',',header=','.join(header),comments='')
        if a.gazebo:
            env=os.environ.copy();env['GZ_PARTITION']='cansat_descent_'+name+'_'+datetime.datetime.now().strftime('%H%M%S')
            reuse=a.reuse and (folder/'gazebo/result.json').exists()
            if reuse:
                archived=load_mission(folder/'gazebo/mission.yaml')
                for key in ['descent','release_height_m','release_yaw_deg','mass_kg','air_density_kgm3','parachute_diameter_m','drag_coefficient']:
                    if archived.get(key)!=cfg.get(key):raise ValueError('Archived run differs: '+name+' / '+key)
            else:
                with (folder/'gazebo.log').open('w') as log:
                    subprocess.run(['bash',str(ROOT/'scripts/start-mission.sh'),'config:='+str(folder/'input.yaml'),'keep_open:=false','rviz:=false','runtime:='+str(folder/'gazebo')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
            result=json.loads((folder/'gazebo/result.json').read_text());landing=result.get('landing')
            check=dict(landed=result['reason']=='landed',camera=result['image_frames']>0,landing_record=landing is not None)
            if landing:
                check.update(time_matches=abs(landing['time_s']-metrics['flight_time_s'])<.8,drift_matches=abs(landing['drift_m']-metrics['drift_m'])<2.,opening_matches=abs(landing['open_fraction']-metrics['open_fraction'])<.05)
            checks[name]=check;gz_runs[name]=np.atleast_2d(np.genfromtxt(folder/'gazebo/descent.csv',delimiter=',',skip_header=1))
            print(name,json.dumps(check),flush=True)
    with (out/'model-summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=summary[0].keys());writer.writeheader();writer.writerows(summary)
    (out/'model-summary.json').write_text(json.dumps(summary,indent=2));plot(runs,out/'model-summary.png','NUMERICAL MODEL ONLY: same equations used by the Gazebo adapter')
    if gz_runs:
        plot(gz_runs,out/'gazebo-summary.png','GAZEBO INTEGRATION: measured positions, commanded model velocity')
        (out/'gazebo-checks.json').write_text(json.dumps(checks,indent=2))
    print(out,flush=True)
    if checks and not all(all(case.values()) for case in checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
