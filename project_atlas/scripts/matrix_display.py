import time,json
from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi,noop
from luma.core.render import canvas
s=spi(port=0,device=0,gpio=noop())
d=max7219(s,cascaded=4,block_orientation=-90,rotate=3)
d.contrast(200)
def get():
 try:
  with open("/tmp/robot_bat.json") as f:
   j=json.load(f)
   return j.get("L",0),j.get("R",0),j.get("pct",50)
 except:return 0,0,50
def dr(L,R):
 t=0.05
 if L>t and R>t:return "fwd"
 if L<-t and R<-t:return "rev"
 if R>t and L<=t:return "rgt"
 if L>t and R<=t:return "lft"
 return "stp"
def show(d2,pct,bon):
 with canvas(d) as c:
  c.line([(0,0),(7,0)],fill="white")
  c.line([(0,13),(7,13)],fill="white")
  c.line([(0,0),(0,13)],fill="white")
  c.line([(7,0),(7,13)],fill="white")
  c.line([(2,14),(5,14)],fill="white")
  c.line([(2,15),(5,15)],fill="white")
  if pct>10 or bon:
   fy=1+int(pct/100*11)
   c.rectangle([(1,1),(6,fy)],fill="white")
  if d2=="fwd":
   c.polygon([(3,31),(0,25),(7,25)],fill="white")
   c.rectangle([(2,17),(5,25)],fill="white")
  elif d2=="rev":
   c.polygon([(3,17),(0,23),(7,23)],fill="white")
   c.rectangle([(2,23),(5,31)],fill="white")
  elif d2=="lft":
   c.polygon([(0,24),(5,19),(5,29)],fill="white")
   c.rectangle([(5,19),(7,29)],fill="white")
  elif d2=="rgt":
   c.polygon([(7,24),(2,19),(2,29)],fill="white")
   c.rectangle([(0,19),(2,29)],fill="white")
  else:
   c.rectangle([(1,19),(6,22)],fill="white")
   c.rectangle([(1,25),(6,28)],fill="white")
n=0
while True:
 L,R,p=get()
 show(dr(L,R),p,(n%4<2))
 n+=1
 time.sleep(0.5)
