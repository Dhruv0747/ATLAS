"""Explicit isolated PC systemd test; fake child only, no ROS or rover URLs."""
import json,os,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path

def child(path):
    proc=subprocess.Popen(['/usr/bin/sleep','30']);Path(path).write_text(str(proc.pid))
    address=os.environ['NOTIFY_SOCKET'];address='\0'+address[1:] if address.startswith('@') else address
    with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:s.sendto(b'READY=1',address)
    time.sleep(30) # deliberately omit watchdog notifications

def test():
    unit='atlas-mapping-fake-'+uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory() as d:
        pid=Path(d)/'pid'
        subprocess.run(['systemd-run','--user','--unit='+unit,'--property=Type=notify','--property=WatchdogSec=1',
                        '--property=TimeoutStopSec=1','--property=KillMode=control-group','--property=Restart=no',
                        sys.executable,str(Path(__file__).resolve()),'child',str(pid)],check=True,capture_output=True)
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                state=subprocess.check_output(['systemctl','--user','show',unit,'-p','Result','-p','ActiveState'],text=True)
                if 'ActiveState=failed' in state:break
                time.sleep(.2)
            assert 'Result=watchdog' in state,state
            assert pid.exists()
            child_pid=int(pid.read_text())
            stat=Path('/proc')/str(child_pid)/'stat'
            assert not stat.exists() or stat.read_text().rsplit(')',1)[1].split()[0]=='Z'
            print(json.dumps(dict(fake_watchdog='PASS',unit=unit,child_stopped=True)))
        finally:
            subprocess.run(['systemctl','--user','stop',unit],capture_output=True)
            subprocess.run(['systemctl','--user','reset-failed',unit],capture_output=True)

if __name__=='__main__':
    child(sys.argv[2]) if len(sys.argv)>1 and sys.argv[1]=='child' else test()
