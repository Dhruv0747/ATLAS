import threading
import time
import json
from collections import defaultdict
from rclpy.publisher import Publisher

def install(cls):
    stats = defaultdict(lambda: [0, 0.0, 0.0])
    def wrap(fn, name):
        def measured(*args, **kwargs):
            start = time.monotonic()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = time.monotonic() - start
                key = name if name else 'publish:' + args[0].topic_name
                row = stats[key]
                row[0] += 1
                row[1] += elapsed
                row[2] = max(row[2], elapsed)
        return measured
    Publisher.publish = wrap(Publisher.publish, None)
    for name in ('_publish_board_state', '_motor_keepalive', '_cal_policy', '_cal_joy', '_on_drive_mode', '_publish_battery'):
        setattr(cls, name, wrap(getattr(cls, name), 'callback:' + name))
    def report():
        while True:
            time.sleep(10)
            rows = {k: list(v) for k, v in list(stats.items())}
            print('CALLBACK_PROBE ' + json.dumps(sorted(rows.items(), key=lambda x:x[1][1], reverse=True)[:12]), flush=True)
    threading.Thread(target=report, daemon=True).start()
