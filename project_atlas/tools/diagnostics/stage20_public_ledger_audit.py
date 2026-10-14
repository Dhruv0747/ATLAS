"""Native read-only audit of exact recorded CDR/receipt pairs and source stamps."""
import hashlib
import json
from pathlib import Path
from stage20_capture import serialized_source_stamp

def audit(directory):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    reader=rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(directory),storage_id='sqlite3'),
                rosbag2_py.ConverterOptions('',''))
    types={x.name:x.type for x in reader.get_all_topics_and_types()}
    pending=None;matched=0;headers=0;lastseq=0
    while reader.has_next():
        topic,raw,receipt=reader.read_next()
        if topic=='/atlas/diagnostics/capture_receipt':
            ledger=json.loads(deserialize_message(raw,get_message(types[topic])).data)
            if pending is None:raise ValueError('orphan receipt')
            t,payload,timestamp=pending
            if t!=ledger['topic'] or hashlib.sha256(payload).hexdigest()!=ledger['payload_sha256']:
                raise ValueError('payload/receipt mismatch')
            if ledger['seq']!=lastseq+1 or ledger['receive_ros_ns']!=timestamp:
                raise ValueError('sequence/receipt timestamp mismatch')
            lastseq=ledger['seq'];message=deserialize_message(payload,get_message(types[t]))
            if hasattr(message,'header'):
                s=message.header.stamp
                if ledger['source_ns']!=s.sec*1000000000+s.nanosec:
                    raise ValueError('source stamp differs from original CDR')
                headers+=1
            elif types[t]=='tf2_msgs/msg/TFMessage' and message.transforms:
                s=message.transforms[0].header.stamp
                if ledger['source_ns']!=s.sec*1000000000+s.nanosec:raise ValueError('TF stamp mismatch')
                headers+=1
            pending=None;matched+=1
        else:
            if pending is not None:raise ValueError('sample without receipt')
            pending=(topic,raw,receipt)
    if pending is not None:raise ValueError('truncated final receipt pair')
    return {'matched_cdr_receipts':matched,'verified_source_headers':headers,
            'exact_payload_hashes':True,'replay_fidelity_verified':False}

if __name__=='__main__':
    import sys
    print(json.dumps(audit(Path(sys.argv[1]))))
