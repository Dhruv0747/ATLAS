import pytest
from atlas_intercom import HEADER,MAGIC,PLAY_STREAM,packet
def test_packet_round_trip():
    raw=packet(PLAY_STREAM,b'\x01\x02',7)
    assert HEADER.unpack(raw[:HEADER.size])==(MAGIC,PLAY_STREAM,0,2,7)
    assert raw[HEADER.size:]==b'\x01\x02'
def test_packet_rejects_oversize():
    with pytest.raises(ValueError): packet(PLAY_STREAM,b'x'*65536)
