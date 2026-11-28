#!/usr/bin/env python3
"""ATLAS: decode the FUNC_REPORT_RC_SBUS (0xE1) packet from the ATLAS-patched Yahboom firmware.

PROPOSAL, NOT DEPLOYED. Read-only telemetry: nothing here can command motors, steering, E-STOP or
the drive mixer. The only output is a Stage 27 /atlas/rc/frames message for the FlySky Test Lab.

Firmware contract (ATLAS patch on vendor ROS-Driver-Board-FW 3.6.5, see
docs/ATLAS_YAHBOOM_SBUS_FIRMWARE_PATCH.md). The packet uses the board's existing framing:

    FF FB len=0x1E type=0xE1 | fmt seq status age10 | sbus[1..23] | checksum

    fmt     0xA1 (layout version)
    seq     uint8, +1 per complete SBUS frame the STM32 received (wraps)
    status  bit0 a frame was ever received, bit1 last frame younger than 100 ms,
            bit2 SBUS frame-lost flag, bit3 SBUS failsafe flag,
            bit4 firmware built with SBUS motor drive compiled OUT (must be 1)
    age10   age of the last frame in 10 ms units, saturating at 255; 255 when none
    sbus    bytes 1..23 of the received 25-byte SBUS frame, unmodified
    checksum sum(bytes[2:-1]) & 0xFF (Rosmaster_Lib validates it before we see the payload)

Safety rules enforced here:
  * A report without the DRIVE_DISABLED bit is rejected and counted: that would mean firmware that can
    still drive from SBUS, which ATLAS must not run.
  * Only NEW frames (seq changed) that are fresh are forwarded, so a stale frame repeated by the 25 Hz
    report can never look LIVE in the Test Lab. When frames stop, nothing is published and the Test
    Lab's own stale/lost timers take over.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_flysky_core as core   # noqa: E402

FUNC_REPORT_RC_SBUS = 0xE1
REPORT_FORMAT = 0xA1
PAYLOAD_LEN = 27            # fmt, seq, status, age10, 23 SBUS bytes
PACKET_LEN = 32             # FF FB len type + payload + checksum
ST_EVER = 1 << 0
ST_FRESH = 1 << 1
ST_FRAME_LOST = 1 << 2
ST_FAILSAFE = 1 << 3
ST_DRIVE_DISABLED = 1 << 4
AGE_NONE = 255


class ReportRejected(ValueError):
    pass


@dataclass(frozen=True)
class RcReport:
    seq: int
    ever: bool
    fresh: bool
    frame_lost: bool
    failsafe: bool
    drive_disabled: bool
    age_ms: Optional[int]       # None when no frame was ever received or the age saturated
    sbus_frame: Optional[bytes]  # the reconstructed 25-byte SBUS frame, None when never received


def parse_payload(payload: Sequence[int]) -> RcReport:
    """payload = Rosmaster_Lib ext_data without its trailing checksum byte."""
    p = bytes(payload)
    if len(p) != PAYLOAD_LEN:
        raise ReportRejected('payload length %d != %d' % (len(p), PAYLOAD_LEN))
    if p[0] != REPORT_FORMAT:
        raise ReportRejected('unknown report format 0x%02X' % p[0])
    seq, status, age10 = p[1], p[2], p[3]
    if not status & ST_DRIVE_DISABLED:
        raise ReportRejected('firmware reports SBUS drive ENABLED; refusing (must never run on ATLAS)')
    ever = bool(status & ST_EVER)
    frame = bytes([core.SBUS_HEADER]) + p[4:27] + b'\x00' if ever else None
    if frame is not None and core.decode_sbus(frame) is None:
        raise ReportRejected('embedded SBUS frame does not decode')
    return RcReport(seq=seq, ever=ever, fresh=bool(status & ST_FRESH),
                    frame_lost=bool(status & ST_FRAME_LOST), failsafe=bool(status & ST_FAILSAFE),
                    drive_disabled=True,
                    age_ms=(age10 * 10 if ever and age10 != AGE_NONE else None), sbus_frame=frame)


def build_packet(sbus_frame: Optional[bytes], seq: int, age_ms: Optional[int],
                 drive_disabled: bool = True) -> bytes:
    """Python mirror of the firmware's SBUS_Build_Report, for tests and the simulator only."""
    ever = sbus_frame is not None
    status = ST_DRIVE_DISABLED if drive_disabled else 0
    if ever:
        status |= ST_EVER
        if age_ms is not None and age_ms < 100:
            status |= ST_FRESH
        if sbus_frame[23] & 4:
            status |= ST_FRAME_LOST
        if sbus_frame[23] & 8:
            status |= ST_FAILSAFE
        age10 = min(255, (age_ms or 0) // 10)
        body = bytes(sbus_frame[1:24])
    else:
        age10, body = AGE_NONE, bytes(23)
    pkt = bytearray([0xFF, 0xFB, PACKET_LEN - 2, FUNC_REPORT_RC_SBUS, REPORT_FORMAT, seq & 0xFF, status, age10])
    pkt += body
    pkt.append(sum(pkt[2:]) & 0xFF)
    return bytes(pkt)


class RcReportForwarder:
    """Turns RC reports into Stage 27 /atlas/rc/frames messages (via the existing bridge rate limiter)."""

    def __init__(self, forwarder: Any):
        self.fwd = forwarder            # atlas_rc_readonly_bridge.FrameForwarder('sbus')
        self.last_seq: Optional[int] = None
        self.reports = 0
        self.rejected = 0
        self.last_reject = ''
        self.stale_or_repeat = 0
        self.never = 0
        self.drive_enabled_seen = False

    def handle(self, payload: Sequence[int], rx: float, wall: float,
               publish: Callable[[Dict[str, Any]], None]) -> int:
        self.reports += 1
        try:
            r = parse_payload(payload)
        except ReportRejected as exc:
            self.rejected += 1
            self.last_reject = str(exc)
            if 'drive ENABLED' in self.last_reject:
                self.drive_enabled_seen = True
            return 0
        if not r.ever:
            self.never += 1
            return 0
        if not r.fresh or r.seq == self.last_seq:
            self.stale_or_repeat += 1
            self.last_seq = r.seq
            return 0
        self.last_seq = r.seq
        return self.fwd.feed(r.sbus_frame, rx, wall, publish)

    def status(self) -> Dict[str, Any]:
        return {'reports': self.reports, 'rejected': self.rejected, 'last_reject': self.last_reject,
                'stale_or_repeat': self.stale_or_repeat, 'never_received': self.never,
                'drive_enabled_firmware_seen': self.drive_enabled_seen}
