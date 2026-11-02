"""Focused Linux-only socket lifecycle checks; no Jetson or production services."""
import socket
import sys
import time
import threading
import urllib.request
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import atlas_health_exporter as E


@pytest.mark.skipif(sys.platform!='linux',reason='Linux IP_FREEBIND')
def test_missing_lan_address_does_not_require_restart():
    with pytest.raises(OSError):E.MonitoringHTTPServer(('192.0.2.200',0),E.Handler)
    server=E.MonitoringHTTPServer(('192.0.2.200',0),E.Handler,freebind=True)
    try:
        assert server.server_address[0]=='192.0.2.200'
        assert server.socket.getsockopt(socket.SOL_IP,15)==1
    finally:server.server_close()


def test_scraper_disconnection_and_stale_cache_recover_without_restart(monkeypatch):
    server=E.MonitoringHTTPServer(('127.0.0.1',0),E.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url='http://127.0.0.1:%s/metrics'%server.server_port
    try:
        client=socket.create_connection(server.server_address);client.close()
        monkeypatch.setattr(E,'LATEST',None);monkeypatch.setattr(E,'LAST',0)
        with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(url,timeout=2)
        assert err.value.code==503
        monkeypatch.setattr(E,'LATEST','atlas_test 1\n');monkeypatch.setattr(E,'LAST',time.monotonic())
        with urllib.request.urlopen(url,timeout=2) as response:assert response.read()==b'atlas_test 1\n'
        assert thread.is_alive()
    finally:server.shutdown();server.server_close();thread.join(2)
