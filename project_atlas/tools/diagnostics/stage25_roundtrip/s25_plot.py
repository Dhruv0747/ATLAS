import math,numpy as np,yaml
from PIL import Image
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from s25_load import load
d=load({'/amcl_pose'})
y=yaml.safe_load(open('/mnt/user-data/uploads/Downloads/atlas_recovery_20261015/atlas_latest.yaml'))
img=np.array(Image.open('/mnt/user-data/uploads/Downloads/atlas_recovery_20261015/atlas_latest.pgm'))
res=y['resolution'];ox,oy=y['origin'][:2];h,w=img.shape
ext=[ox,ox+w*res,oy,oy+h*res]
fig,ax=plt.subplots(figsize=(9,8.5))
ax.imshow(img,cmap='gray',extent=ext,origin='upper')
t0=d['/amcl_pose'][0][0]
P=np.array([(t-t0,m.pose.pose.position.x,m.pose.pose.position.y) for t,m,_ in d['/amcl_pose']])
sc=ax.scatter(P[:,1],P[:,2],c=P[:,0],s=7,cmap='viridis',zorder=3); plt.colorbar(sc,label='s since 21:36:55 IST',shrink=.6)
for lab,t in (('start',2),('Hall stop',57),('end',438)):
    i=np.abs(P[:,0]-t).argmin(); ax.plot(P[i,1],P[i,2],'r*',ms=14,zorder=4); ax.annotate(lab,(P[i,1],P[i,2]),color='red',xytext=(6,6),textcoords='offset points',weight='bold')
ax.add_patch(plt.Rectangle((-0.7,-2.8),1.4,1.9,fill=False,ec='orange',lw=2)); ax.annotate('Dhruv Room search box',(-0.7,-2.9),color='orange')
ax.set_xlim(-4,8);ax.set_ylim(-6,3.5);ax.set_aspect('equal');ax.set_title('Stage 25 loop: AMCL track on accepted map')
fig.savefig('s25_track.png',dpi=90,bbox_inches='tight'); print(ext)
