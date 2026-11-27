"""Inspectable scientific plot for a saved simulation case."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image

def plot(folder):
    folder=Path(folder)
    if not (folder/'result.json').exists():return
    r=json.loads((folder/'result.json').read_text())
    fig,axes=plt.subplots(2,2,figsize=(12,9))
    if (folder/'left.png').exists():axes[0,0].imshow(Image.open(folder/'left.png'))
    axes[0,0].set_title('Rectified left image (first capture)');axes[0,0].axis('off')
    if (folder/'cloud.npz').exists():
        xyz=np.load(folder/'cloud.npz')['xyz'];sel=(xyz[:,0]>=-.2)&(xyz[:,0]<=4)&(abs(xyz[:,1])<=3)
        xyz=xyz[sel]
        cloud=axes[0,1].scatter(xyz[:,0],xyz[:,1],c=xyz[:,2],s=2,vmin=0,vmax=.7,cmap='viridis')
        fig.colorbar(cloud,ax=axes[0,1],label='Map height z [m]')
    axes[0,1].set_title('Reconstructed cloud: top view (not a solid surface)')
    axes[0,1].set_xlabel('x [m]');axes[0,1].set_ylabel('y [m]');axes[0,1].set_aspect('equal');axes[0,1].grid(True)
    csv=folder/'trajectory.csv'
    if csv.exists() and r.get('matched_samples',0)>0:
        data=np.atleast_2d(np.genfromtxt(csv,delimiter=',',skip_header=1))
        def relative(points):
            c,s=np.cos(points[0,3]),np.sin(points[0,3]);result=points[:,:3]-points[0,:3]
            result[:,:2]=result[:,:2]@np.array([[c,-s],[s,c]])
            return result
        est=relative(data[:,1:5]);truth=relative(data[:,5:9])
        axes[1,0].plot(truth[:,0],truth[:,1],label='Gazebo truth',lw=2)
        axes[1,0].plot(est[:,0],est[:,1],'.-',label='Stereo odometry',markersize=3)
        axes[1,0].legend();axes[1,0].set_aspect('equal');axes[1,0].grid(True)
        axes[1,1].plot(data[:,0]-data[0,0],np.linalg.norm(est-truth,axis=1)*1000)
    axes[1,0].set_title('Trajectory after initial-pose alignment');axes[1,0].set_xlabel('x [m]');axes[1,0].set_ylabel('y [m]')
    axes[1,1].set_title('Position error at matched timestamps');axes[1,1].set_xlabel('Simulation time [s]');axes[1,1].set_ylabel('Error [mm]');axes[1,1].grid(True)
    fig.suptitle(f"{r.get('surface','')} / {r.get('mode','')} | poses={r.get('matched_samples',0)}, cloud={r.get('cloud_points',0)}\nSynthetic grass, ideal pinhole lens; no real-world accuracy claim")
    fig.tight_layout();fig.savefig(folder/'overview.png',dpi=160);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();plot(a.folder)
