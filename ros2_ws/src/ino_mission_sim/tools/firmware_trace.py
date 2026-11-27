"""Execute actual native firmware against synthetic sensor traces (not Gazebo).

The stationary and descent traces isolate decisions. They do not model feedback
from motor commands, so this is never reported as an end-to-end mission success.
"""
import argparse,csv,json,subprocess,tempfile
from pathlib import Path
import numpy as np
from sensor_faults import SensorBank,NAMES

ROOT=Path(__file__).resolve().parents[1]

def run(profile,folder,hold_only=False,duration=66.,sensors=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    frame=folder/'trace.rgb565';pixels=np.zeros((120,160),dtype='<u2');pixels[:,72:88]=0xf800;pixels.tofile(frame)
    bank=SensorBank(sensors or {},27);rows=[];t=0.;last_tick=-.02
    def sample(until):
        nonlocal last_tick
        while last_tick+.02<=until+1e-8:
            last_tick=round(last_tick+.02,6)
            h=30. if hold_only or last_tick<8 else max(0.,30.-5*(last_tick-8))
            values=dict(barometer=[h,20.,1013.25],gnss=[0.,0.],imu=[0.,0.,0.],heading=[90.],camera=str(frame))
            for name,value in values.items():bank.channels[name].push(last_tick,value)
        return bank.read(until)
    def packet(observed):
        def value(name,fallback):return observed[name]['value'] if observed[name]['value'] is not None else fallback
        alt,temp,pressure=value('barometer',[30.,20.,1013.25]);x,y=value('gnss',[0.,0.]);ax,ay,az=value('imu',[0.,0.,0.]);yaw=value('heading',[90.])[0]
        mask=sum((1<<i) for i,name in enumerate(NAMES) if observed[name]['valid'])
        stamps=[round(observed[name]['stamp_s']*1000) if observed[name]['stamp_s'] is not None else -1 for name in NAMES]
        return [round(t*1000),alt,temp,pressure,30.3741226+y/110946.252,130.9599762+x/96000.,yaw,ax,ay,az,value('camera','-'),mask,*stamps]
    proc=subprocess.Popen([str(ROOT/'firmware/sil/build'/profile/'legacy_sil')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        for _ in range(100000):
            fields=proc.stdout.readline().split()
            if not fields:raise RuntimeError('Native firmware exited: '+proc.stderr.read())
            if fields[0] not in ('WAIT','WAITG'):continue
            wait,action,separation,phase=map(int,fields[1:5]);stage=int(fields[7]) if fields[0]=='WAITG' else -1;health=int(fields[8]) if fields[0]=='WAITG' else -1
            rows.append(dict(time_s=t,action=action,separation=separation,phase=phase,guard_stage=stage,health_mask=health))
            if t>=duration:break
            t+=wait/1000.;observed=sample(t)
            proc.stdin.write(' '.join(map(str,packet(observed)))+'\n');proc.stdin.flush()
        else:raise RuntimeError('Native firmware did not advance trace time')
        proc.stdin.write('STOP\n');proc.stdin.flush();proc.wait(timeout=3)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        for stream in [proc.stdin,proc.stdout,proc.stderr]:stream.close()
    landing_truth=None if hold_only else 14.
    first=lambda key,next_value:next((r['time_s'] for r in rows if r[key]==next_value),None)
    result=dict(evidence='native C++ with synthetic sensor traces; no Gazebo or motor feedback',profile=profile,
                first_separation_s=first('separation',1),first_guard_landed_s=first('guard_stage',2),
                premature_separation=any(r['separation'] and (hold_only or r['time_s']<landing_truth) for r in rows),
                premature_motion=any(r['action'] and (hold_only or r['time_s']<landing_truth) for r in rows),
                unsafe_stale_motion=any(r['action'] and r['health_mask'] not in (-1,31) for r in rows),sensor_counts=bank.counts())
    (folder/'result.json').write_text(json.dumps(result,indent=2))
    with (folder/'commands.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    return result,rows

def suite(folder):
    folder=Path(folder);results={}
    for name,profile,held,sensors in [
        ('original_wait','original',True,{}),('guarded_wait','guarded',True,{}),
        ('guarded_descent','guarded',False,{}),
        ('guarded_gnss_loss','guarded',False,{'gnss':{'blackouts':[[52.,63.]]}}),
        ('guarded_camera_delay','guarded',False,{'camera':{'delay_s':1.}}),
        ('guarded_baro_loss','guarded',False,{'barometer':{'blackouts':[[10.,30.]]}}),
    ]:results[name]=run(profile,folder/name,held,sensors=sensors)[0]
    checks=dict(original_hazard_reproduced=results['original_wait']['premature_separation'],
                waiting_does_not_arm=results['guarded_wait']['first_guard_landed_s'] is None,
                landing_after_ground=results['guarded_descent']['first_guard_landed_s']>=15.9,
                no_early_outputs=all(not r['premature_separation'] and not r['premature_motion'] for n,r in results.items() if n!='original_wait'),
                stale_stops=all(not r['unsafe_stale_motion'] for n,r in results.items() if n.startswith('guarded')),
                delayed_camera_no_drive=not any(r['action'] for r in run('guarded',folder/'camera_delay_repeat',sensors={'camera':{'delay_s':1.}})[1]))
    (folder/'summary.json').write_text(json.dumps(dict(checks=checks,cases=results),indent=2));print(json.dumps(checks,indent=2))
    if not all(checks.values()):raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(ROOT/'logs/firmware-trace-tests'));suite(parser.parse_args().out)
