"""Transport-free PC CDR storage feasibility test. Never connects to ATLAS.

Not a deployed recorder: live discovery/QoS/native Humble readback remain gates.
Reuses Stage20 topic inventory and source stamp extraction, not its live runner.
"""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import tracemalloc

from rosbags.rosbag2 import Writer
from rosbags.typesys import Stores, get_typestore
from stage20_capture import TOPIC_LIST, serialized_source_stamp


class StorageProbe:
    def __init__(self, path, types, quota=500*1024**2):
        self.path = Path(path)
        if self.path.exists():
            raise ValueError('new isolated output directory required')
        if not 1024**2 <= quota <= 500*1024**2:
            raise ValueError('quota outside prototype limits')
        if set(types)-set(TOPIC_LIST):
            raise ValueError('topic outside existing recorder inventory')
        self.quota = quota
        self.store = get_typestore(Stores.ROS2_HUMBLE)
        self.writer = Writer(self.path, version=8)
        self.writer.open()
        self.closed = False
        self.count = 0
        try:
            self.connections = {t:self.writer.add_connection(t, k, typestore=self.store)
                                for t,k in types.items()}
            self.ledger = (self.path/'receipts.jsonl').open('x', encoding='utf-8')
        except BaseException:
            self.writer.close()
            self.closed = True
            raise

    def size(self):
        return sum(p.stat().st_size for p in self.path.rglob('*') if p.is_file())

    def write(self, topic, payload, pc_receive_ns):
        if self.closed:
            raise ValueError('closed')
        con = self.connections[topic]
        raw = bytes(payload)
        # Conservative per-write reservation. No retention deletion, ever.
        if self.size()+len(raw)*2+65536 > self.quota:
            raise RuntimeError('quota admission refused')
        self.writer.write(con, pc_receive_ns, raw)
        self.ledger.write(json.dumps({'topic':topic,'pc_receive_ns':pc_receive_ns,
            'source_header_ns':serialized_source_stamp(raw,con.msgtype),
            'sha256':hashlib.sha256(raw).hexdigest(),
            'sequence_gap':'UNKNOWN','clock_offset_ns':None})+'\n')
        self.ledger.flush()
        self.count += 1

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.writer.close()
            finally:
                self.ledger.close()


def validate(path):
    path = Path(path)
    ledger = [json.loads(x) for x in (path/'receipts.jsonl').read_text().splitlines()]
    with closing(sqlite3.connect('file:'+str(next(path.glob('*.db3')))+'?mode=ro', uri=True)) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        actual = db.execute('SELECT topics.name, topics.type, messages.timestamp, messages.data '
                            'FROM messages JOIN topics ON topics.id=messages.topic_id '
                            'ORDER BY messages.id').fetchall()
    assert len(actual) == len(ledger)
    for (topic, kind, stamp, data), row in zip(actual,ledger):
        assert (topic,stamp,hashlib.sha256(data).hexdigest()) == (
            row['topic'],row['pc_receive_ns'],row['sha256'])
        assert serialized_source_stamp(data,kind) == row['source_header_ns']
    return len(actual)


def main():
    import numpy as np
    with tempfile.TemporaryDirectory(prefix='atlas-offboard-synthetic-') as td:
        types={'/scan':'sensor_msgs/msg/LaserScan',
               **{'/yahboom/encoder/m'+str(i):'std_msgs/msg/Int32' for i in range(1,5)}}
        sink=StorageProbe(Path(td)/'bag',types)
        t=sink.store.types
        scan=t['sensor_msgs/msg/LaserScan'](t['std_msgs/msg/Header'](
            t['builtin_interfaces/msg/Time'](123,456),'laser'),
            -3.14,3.14,.01,0.,.1,.1,20.,np.ones(720,dtype=np.float32),np.empty(0,dtype=np.float32))
        payloads={'/scan':sink.store.serialize_cdr(scan,types['/scan'])}
        for topic,kind in types.items():
            if topic!='/scan':payloads[topic]=sink.store.serialize_cdr(t[kind](123),kind)
        tracemalloc.start()
        start=time.perf_counter(); cpu=time.process_time()
        try:
            for step in range(1500):
                for topic,raw in payloads.items():
                    if topic!='/scan' or step%5==0:
                        sink.write(topic,raw,time.time_ns())
                time.sleep(max(0.,start+(step+1)*.02-time.perf_counter()))
        finally:
            sink.close()
        elapsed=time.perf_counter()-start; used=time.process_time()-cpu
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        count=validate(sink.path)
        print(json.dumps({'wall_s':elapsed,'cpu_s':used,'one_core_cpu_pct':100*used/elapsed,
            'python_peak_bytes':peak,'disk_bytes':sink.size(),'messages_verified':count,
            'topics':5,'full_required_topic_coverage':False,'network_tested':False,
            'native_humble_readback_tested':False,'clock_offset_ns':None},indent=2))


if __name__=='__main__':
    main()
