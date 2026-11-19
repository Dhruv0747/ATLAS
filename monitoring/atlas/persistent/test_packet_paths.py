#!/usr/bin/env python3
"""Run ONLY inside `unshare --net`: fake TCP listeners, no host/Jetson firewall edits."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

HERE=Path(__file__).resolve().parent

def run(*args):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=5).strip()

def server(family, address):
    s=socket.socket(family,socket.SOCK_STREAM)
    if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
    s.bind(address);s.listen()
    def serve():
        while True:
            try:c,_=s.accept();c.close()
            except OSError:return
    threading.Thread(target=serve,daemon=True).start()
    return s

def main():
    assert os.geteuid()==0
    assert os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net'), 'must use isolated net namespace'
    child=subprocess.Popen(['unshare','--net','python3','-u','-c',
                            'import time; print("READY",flush=True); time.sleep(120)'],stdout=subprocess.PIPE,text=True)
    sockets=[]
    try:
        assert child.stdout.readline().strip()=='READY'
        ns=['nsenter','-t',str(child.pid),'-n']
        run('ip','link','set','lo','up');run(*ns,'ip','link','set','lo','up')
        run('ip','link','add','wlP1p1s0','type','veth','peer','name','client0')
        run('ip','link','set','client0','netns',str(child.pid))
        run('ip','addr','add','192.168.1.16/24','dev','wlP1p1s0')
        run('ip','-6','addr','add','fd00::16/64','dev','wlP1p1s0','nodad')
        run('ip','link','set','wlP1p1s0','up')
        for address in ('192.168.1.6/24','192.168.1.7/24'):
            run(*ns,'ip','addr','add',address,'dev','client0')
        run(*ns,'ip','-6','addr','add','fd00::6/64','dev','client0','nodad')
        run(*ns,'ip','link','set','client0','up')
        for family,addr in [(socket.AF_INET,('0.0.0.0',9118)),(socket.AF_INET,('0.0.0.0',8088)),
                            (socket.AF_INET6,('::',9118))]:sockets.append(server(family,addr))
        # Legacy Tailscale-shaped ACCEPT must not bypass the earlier nft DROP.
        run('iptables-legacy','-N','ts-input');run('iptables-legacy','-A','ts-input','-j','ACCEPT')
        run('iptables-legacy','-I','INPUT','1','-j','ts-input')
        run('nft','add','table','inet','unrelated_test')
        run('nft','-c','-f',str(HERE/'atlas-monitor.nft'));run('nft','-f',str(HERE/'atlas-monitor.nft'))
        spec=importlib.util.spec_from_file_location('guard',HERE/'guard.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        guard.verify_firewall()
        def connect(source,destination,port,ipv6=False):
            code='import socket,json; s=socket.socket('+('socket.AF_INET6' if ipv6 else 'socket.AF_INET')+'); s.settimeout(.3); s.bind(('+repr(source)+',0)); print(s.connect_ex(('+repr(destination)+','+str(port)+')) == 0)'
            return run(*ns,'python3','-c',code)=='True'
        outcomes={
            'permitted_windows':connect('192.168.1.6','192.168.1.16',9118),
            'denied_other_source':not connect('192.168.1.7','192.168.1.16',9118),
            'denied_ipv6':not connect('fd00::6','fd00::16',9118,True),
            'unrelated_port_preserved':connect('192.168.1.7','192.168.1.16',8088)}
        # Parent localhost is not the permitted Wi-Fi interface/source.
        local=socket.socket();local.settimeout(.3)
        outcomes['denied_loopback']=local.connect_ex(('127.0.0.1',9118))!=0;local.close()
        run('nft','delete','table','inet','atlas_monitor')
        outcomes['rollback_other_source_restored']=connect('192.168.1.7','192.168.1.16',9118)
        outcomes['unrelated_nft_preserved']='unrelated_test' in run('nft','list','tables')
        outcomes['legacy_rules_preserved']='-A INPUT -j ts-input' in run('iptables-legacy','-S','INPUT')
        assert all(outcomes.values()),outcomes
        print(json.dumps(outcomes,indent=2))
    finally:
        for s in sockets:s.close()
        child.terminate();child.wait(timeout=5)

if __name__=='__main__':main()
