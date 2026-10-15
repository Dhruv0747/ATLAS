"""Exercise the outbound boundary without any sockets or production data."""
import json
import struct
import unittest
from offboard_bridge_contract import (TOPICS, ReadOnlySender, select_channels,
                                      validate_operation, message_data)


class Contract(unittest.TestCase):
    def setUp(self):
        self.channels = [dict(id=i, topic=t, schemaName=k, encoding='cdr', schema='schema')
                         for i, (t, k) in enumerate(TOPICS.items(), 50)]
        self.subscriptions = select_channels(self.channels)

    def test_only_subscribe_unsubscribe_can_reach_sender(self):
        wire = []
        client = ReadOnlySender(wire.append, self.subscriptions)
        client.subscribe(); client.unsubscribe()
        self.assertEqual([json.loads(x)['op'] for x in wire], ['subscribe', 'unsubscribe'])
        with self.assertRaises(ValueError): client.subscribe()
        self.assertEqual(len(wire), 2)

    def test_forbidden_operations_binary_and_extra_fields(self):
        for op in ('advertise','unadvertise','publish','setParameters','getParameters',
                   'subscribeParameterUpdates','subscribeConnectionGraph','fetchAsset',
                   'serviceCall','sendGoal',None):
            with self.subTest(op=op), self.assertRaises(ValueError):
                validate_operation({'op':op}, self.subscriptions)
        for message in (b'\x01control', {'op':'subscribe','subscriptions':[], 'extra':'payload'},
                        {'op':'unsubscribe','subscriptionIds':[999]}):
            with self.assertRaises(ValueError):validate_operation(message,self.subscriptions)

    def test_missing_duplicate_or_wrong_schema_refused(self):
        for channels in (self.channels[:-1],self.channels+[self.channels[0]],
                         [dict(c,encoding='json') for c in self.channels],
                         [dict(c,schemaName='wrong') for c in self.channels]):
            with self.assertRaises(ValueError):select_channels(channels)

    def test_binary_payload_and_server_timestamp_preserved(self):
        payload=b'\x00\x01\x00\x00raw CDR bytes'
        frame=struct.pack('<BIQ',1,1,123456789)+payload
        self.assertEqual(message_data(frame,self.subscriptions),('/scan',123456789,payload))
        for bad in (frame[:12],struct.pack('<BIQ',3,1,123)+payload,
                    struct.pack('<BIQ',1,999,123)+payload):
            with self.assertRaises(ValueError):message_data(bad,self.subscriptions)


if __name__=='__main__':unittest.main()
