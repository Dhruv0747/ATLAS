#!/usr/bin/env python3
"""ATLAS on-demand WebRTC intercom with exclusive ESP32 audio ownership."""
import argparse, asyncio, struct, subprocess, threading
from fractions import Fraction

MAGIC=0x534C5441; HEADER=struct.Struct("<IBBHI")
MIC_PCM,COMMAND,PLAY_STREAM=1,0x82,0x85; SAMPLE_RATE=16000
SERIAL_DEFAULT="/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_28:84:85:57:02:24-if00"

def packet(kind,payload=b"",sequence=0):
    if len(payload)>65535: raise ValueError("payload is too large")
    return HEADER.pack(MAGIC,kind,0,len(payload),sequence)+payload

class AudioOwner:
    """AI voice and Live Call can never own the serial device together."""
    def __init__(self,device=SERIAL_DEFAULT):
        self.device=device; self.serial=None; self.mode="ai_voice"; self.loop=None; self.queue=None; self.lock=threading.Lock()
    @staticmethod
    def service(verb):
        return subprocess.run(["systemctl","--user",verb,"atlas-voice-companion.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode==0
    def start(self,loop,queue):
        import serial
        with self.lock:
            if self.mode=="live_call": return
            if not self.service("stop"): raise RuntimeError("AI voice did not release audio")
            try:
                self.serial=serial.Serial(self.device,921600,timeout=.2); self.loop=loop; self.queue=queue; self.mode="live_call"
                self.write(COMMAND,b"STATE CALL")
                threading.Thread(target=self.read_loop,daemon=True).start()
            except Exception:
                self.mode="ai_voice"; self.service("start"); raise
    def stop(self):
        with self.lock:
            if self.serial:
                try: self.write(COMMAND,b"STATE IDLE"); self.serial.close()
                except Exception: pass
            self.serial=None; self.mode="ai_voice"
        self.service("start")
    def write(self,kind,payload):
        if self.serial: self.serial.write(packet(kind,payload))
    def read_loop(self):
        data=bytearray()
        while self.mode=="live_call" and self.serial:
            try:
                data.extend(self.serial.read(4096))
                while len(data)>=HEADER.size:
                    magic,kind,_f,size,_seq=HEADER.unpack_from(data)
                    if magic!=MAGIC: del data[0]; continue
                    if len(data)<HEADER.size+size: break
                    payload=bytes(data[HEADER.size:HEADER.size+size]); del data[:HEADER.size+size]
                    if kind==MIC_PCM: self.loop.call_soon_threadsafe(self.enqueue,payload)
            except Exception: break
    def enqueue(self,payload):
        if self.queue.full():
            try: self.queue.get_nowait()
            except asyncio.QueueEmpty: pass
        self.queue.put_nowait(payload)

PAGE='''<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><style>body{background:#030914;color:#def7ff;font:16px system-ui;text-align:center}.c{max-width:650px;margin:5vh auto;padding:25px;border:1px solid #16bfff;border-radius:18px;background:#071528}button{font-size:18px;padding:16px 24px;margin:8px;border:0;border-radius:12px;color:white;background:#087cca}.end{background:#c24}audio{width:100%}</style><div class=c><h1>ATLAS LIVE CALL</h1><p id=s>AI Voice mode — microphone private</p><audio id=a autoplay></audio><button id=b>Start secure call</button><button id=e class=end disabled>End call</button></div><script>let pc,st;b.onclick=async()=>{try{st=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});pc=new RTCPeerConnection();st.getTracks().forEach(t=>pc.addTrack(t,st));pc.ontrack=x=>a.srcObject=x.streams[0];await fetch('/api/start',{method:'POST'});let o=await pc.createOffer();await pc.setLocalDescription(o);await new Promise(r=>{if(pc.iceGatheringState==='complete')r();else pc.onicegatheringstatechange=()=>pc.iceGatheringState==='complete'&&r()});let z=await fetch('/offer',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(pc.localDescription)}).then(x=>x.json());await pc.setRemoteDescription(z);s.textContent='LIVE — rover microphone and speaker active';s.style.color='#ff4058';b.disabled=true;e.disabled=false}catch(x){s.textContent='Call failed: '+x;fetch('/api/stop',{method:'POST'})}};e.onclick=async()=>{if(pc)pc.close();if(st)st.getTracks().forEach(t=>t.stop());await fetch('/api/stop',{method:'POST'});s.textContent='AI Voice mode — microphone private';s.style.color='';b.disabled=false;e.disabled=true};onbeforeunload=()=>navigator.sendBeacon('/api/stop')</script>'''

async def create_app(owner):
    from aiohttp import web
    from aiortc import MediaStreamTrack,RTCPeerConnection,RTCSessionDescription
    from av import AudioFrame
    peers=set(); mic=asyncio.Queue(maxsize=20)
    class RoverMic(MediaStreamTrack):
        kind="audio"
        def __init__(self): super().__init__(); self.pos=0
        async def recv(self):
            pcm=await mic.get(); f=AudioFrame(format="s16",layout="mono",samples=len(pcm)//2); f.planes[0].update(pcm); f.sample_rate=SAMPLE_RATE; f.time_base=Fraction(1,SAMPLE_RATE); f.pts=self.pos; self.pos+=len(pcm)//2; return f
    async def index(_): return web.Response(text=PAGE,content_type="text/html")
    async def state(_): return web.json_response({"mode":owner.mode,"privacy_led":owner.mode=="live_call"})
    async def start(_): owner.start(asyncio.get_running_loop(),mic); return web.json_response({"ok":True})
    async def stop(_):
        for pc in list(peers): await pc.close()
        peers.clear(); owner.stop(); return web.json_response({"ok":True})
    async def play(track):
        from av.audio.resampler import AudioResampler
        rs=AudioResampler(format="s16",layout="mono",rate=SAMPLE_RATE)
        while owner.mode=="live_call":
            try:
                for f in rs.resample(await track.recv()): owner.write(PLAY_STREAM,bytes(f.planes[0]))
            except Exception: break
    async def offer(req):
        d=await req.json(); pc=RTCPeerConnection(); peers.add(pc); pc.addTrack(RoverMic())
        @pc.on("track")
        def track(t):
            if t.kind=="audio": asyncio.create_task(play(t))
        @pc.on("connectionstatechange")
        async def changed():
            if pc.connectionState in {"failed","closed","disconnected"}:
                await pc.close(); peers.discard(pc)
                if not peers: owner.stop()
        await pc.setRemoteDescription(RTCSessionDescription(sdp=d["sdp"],type=d["type"])); ans=await pc.createAnswer(); await pc.setLocalDescription(ans)
        return web.json_response({"sdp":pc.localDescription.sdp,"type":pc.localDescription.type})
    app=web.Application(); app.add_routes([web.get('/',index),web.get('/api/state',state),web.post('/api/start',start),web.post('/api/stop',stop),web.post('/offer',offer)]); app.on_cleanup.append(lambda _: asyncio.to_thread(owner.stop)); return app

def main():
    p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8091); p.add_argument('--device',default=SERIAL_DEFAULT); a=p.parse_args()
    from aiohttp import web
    web.run_app(create_app(AudioOwner(a.device)),host='127.0.0.1',port=a.port)
if __name__=='__main__': main()
