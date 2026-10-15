"""Outbound Foxglove operation gate for the approved five-topic stationary probe.

The only application sends available through ReadOnlySender are validated JSON
subscribe/unsubscribe operations. WebSocket handshake/close/pong control frames
are transport operations, not ROS publications. No production connection here.
"""
import json
import struct

TOPICS = {
    '/scan': 'sensor_msgs/msg/LaserScan',
    '/im10a/imu/unvalidated': 'sensor_msgs/msg/Imu',
    '/atlas/encoder_update': 'std_msgs/msg/String',
    '/atlas/control_policy': 'std_msgs/msg/String',
    '/cmd_vel': 'geometry_msgs/msg/Twist',
}


def select_channels(channels):
    selected = {}
    for channel in channels:
        topic = channel.get('topic')
        if topic not in TOPICS:
            continue
        if topic in selected:
            raise ValueError('duplicate diagnostic channel: ' + topic)
        identifier = channel.get('id')
        if type(identifier) is not int or not 0 <= identifier < 2**32:
            raise ValueError('invalid channel id')
        if (channel.get('encoding') != 'cdr' or
                channel.get('schemaName') != TOPICS[topic] or
                not isinstance(channel.get('schema'), str) or not channel['schema']):
            raise ValueError('diagnostic schema mismatch: ' + topic)
        selected[topic] = identifier
    if set(selected) != set(TOPICS) or len(set(selected.values())) != len(TOPICS):
        raise ValueError('missing/ambiguous required diagnostic channels')
    return {index: (topic, selected[topic])
            for index, topic in enumerate(TOPICS, start=1)}


def validate_operation(message, subscriptions):
    if not isinstance(message, dict):
        raise ValueError('application sends must be JSON objects')
    if message.get('op') == 'subscribe':
        expected = [{'id': sid, 'channelId': channel}
                    for sid, (_, channel) in subscriptions.items()]
        if set(message) != {'op', 'subscriptions'} or message['subscriptions'] != expected:
            raise ValueError('subscription list is not the exact approved five topics')
    elif message.get('op') == 'unsubscribe':
        if (set(message) != {'op', 'subscriptionIds'} or
                message['subscriptionIds'] != list(subscriptions)):
            raise ValueError('unsubscribe list must match this connection')
    else:
        raise ValueError('application operation forbidden: ' + str(message.get('op')))
    return json.dumps(message, separators=(',', ':'), allow_nan=False)


class ReadOnlySender:
    def __init__(self, text_sender, subscriptions):
        self._send_text = text_sender
        self.subscriptions = subscriptions
        self.operations = []
        self.subscribed = False

    def subscribe(self):
        if self.operations:
            raise ValueError('one subscription attempt only')
        message = {'op': 'subscribe', 'subscriptions': [
            {'id': sid, 'channelId': channel}
            for sid, (_, channel) in self.subscriptions.items()]}
        self._send_text(validate_operation(message, self.subscriptions))
        self.operations.append(message)
        self.subscribed = True

    def unsubscribe(self):
        if not self.subscribed:
            raise ValueError('no active subscription')
        message = {'op': 'unsubscribe', 'subscriptionIds': list(self.subscriptions)}
        self._send_text(validate_operation(message, self.subscriptions))
        self.operations.append(message)
        self.subscribed = False


def message_data(frame, subscriptions):
    if not isinstance(frame, bytes) or not 13 <= len(frame) <= 2*1024**2:
        raise ValueError('invalid/oversized binary message')
    opcode, sid, server_ns = struct.unpack_from('<BIQ', frame)
    if opcode != 1 or sid not in subscriptions:
        raise ValueError('unexpected binary opcode/subscription')
    topic, _ = subscriptions[sid]
    return topic, server_ns, frame[13:]
