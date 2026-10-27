"""SIMULATION ONLY: stub rclpy for running atlas_dds_storm_probe.py offline. Records entities like Humble rclpy:
create_node adds /rosout + /parameter_events publishers and 6 parameter services. Fault switches via env:
STUB_HANG_IMPORT, STUB_HANG_NODE, STUB_CLIENT, STUB_LEAK_SHM=<dir>, STUB_BURN_S."""
import os
import time

if os.environ.get('STUB_HANG_IMPORT'):
    while True:                      # simulates an import stuck under CPU starvation (only SIGALRM/kill ends it)
        time.sleep(0.05)

PARAM_SERVICES = ('describe_parameters', 'get_parameter_types', 'get_parameters', 'list_parameters',
                  'set_parameters', 'set_parameters_atomically')


def init():
    pass


def shutdown():
    pass


def _resolve(ns, name):
    return name if name.startswith('/') else f'{ns.rstrip("/")}/{name}'


class Node:
    def __init__(self, name, namespace):
        if os.environ.get('STUB_HANG_NODE'):
            while True:
                time.sleep(0.05)
        self.name, self.ns = name, namespace
        self.pubs = ['/rosout', '/parameter_events']
        self.subs, self.clients = [], []
        self.services = [f'{namespace}/{name}/{s}' for s in PARAM_SERVICES]
        if os.environ.get('STUB_LEAK_SHM'):
            open(os.path.join(os.environ['STUB_LEAK_SHM'], f'fastrtps_stub_{os.getpid()}'), 'w').close()
        burn = float(os.environ.get('STUB_BURN_S', '0'))
        end = time.monotonic() + burn
        while time.monotonic() < end:
            pass
        if os.environ.get('STUB_CLIENT'):
            self.clients.append(f'{namespace}/forbidden_client')

    def create_subscription(self, typ, topic, cb, qos):
        self.subs.append(_resolve(self.ns, topic))
        return object()

    def create_publisher(self, typ, topic, qos):
        self.pubs.append(_resolve(self.ns, topic))
        return object()

    def _by(self, items, name, ns):
        assert (name, ns) == (self.name, self.ns)
        return [(i, ['std_msgs/msg/String']) for i in items]

    def get_publisher_names_and_types_by_node(self, name, ns):
        return self._by(self.pubs, name, ns)

    def get_subscriber_names_and_types_by_node(self, name, ns):
        return self._by(self.subs, name, ns)

    def get_service_names_and_types_by_node(self, name, ns):
        return self._by(self.services, name, ns)

    def get_client_names_and_types_by_node(self, name, ns):
        return self._by(self.clients, name, ns)

    def destroy_node(self):
        pass


def create_node(name, namespace=''):
    return Node(name, namespace)
