#!/usr/bin/env python3
"""Stage 28 (proposal): teach Rosmaster_Lib.py to STORE the ATLAS RC report (type 0xE1). Additive.

The receive thread only keeps the latest payload and a counter; nothing is sent to the board and no
existing branch changes. Firmware without the patch never sends 0xE1, so behaviour is unchanged there.
Usage: insert_rosmaster_rc.py <Rosmaster_Lib.py>   (refuses if an anchor is missing or already patched)
"""
import sys

MARK = 'FUNC_REPORT_RC_SBUS'
EDITS = [
    ("        self.FUNC_REPORT_ICM_RAW = 0x0E\n",
     "        self.FUNC_REPORT_ICM_RAW = 0x0E\n"
     "        # ATLAS Stage 28 (proposal): raw SBUS report from ATLAS-patched firmware only.\n"
     "        # Stored, never acted on; older firmware simply never sends it.\n"
     "        self.FUNC_REPORT_RC_SBUS = 0xE1\n"),
    ("        self.__read_car_type = 0\n\n        if self.__debug:",
     "        self.__read_car_type = 0\n"
     "        self._rc_sbus_report = None   # ATLAS Stage 28: (payload bytes, monotonic stamp)\n"
     "        self._rc_sbus_reports = 0\n\n        if self.__debug:"),
    ("            self._serial_diagnostics['last_encoder_packet_stamp'] = self._encoder_sample[1]\n\n        else:",
     "            self._serial_diagnostics['last_encoder_packet_stamp'] = self._encoder_sample[1]\n\n"
     "        # ATLAS Stage 28: read-only RC telemetry. Store the payload (checksum byte dropped) for the\n"
     "        # owner node to decode; no state here influences any command.\n"
     "        elif ext_type == self.FUNC_REPORT_RC_SBUS:\n"
     "            self._rc_sbus_report = (bytes(ext_data[:-1]), time.monotonic())\n"
     "            self._rc_sbus_reports += 1\n\n        else:"),
    ("    def get_serial_diagnostics(self):\n",
     "    def get_rc_sbus_report(self):\n"
     "        \"\"\"ATLAS Stage 28: latest raw RC report as (payload, monotonic stamp, count), or None.\"\"\"\n"
     "        report = self._rc_sbus_report\n"
     "        if report is None:\n"
     "            return None\n"
     "        return report[0], report[1], self._rc_sbus_reports\n\n"
     "    def get_serial_diagnostics(self):\n"),
]


def patch(text: str) -> str:
    if MARK in text:
        raise SystemExit('already patched')
    for old, new in EDITS:
        if text.count(old) != 1:
            raise SystemExit('anchor not unique/missing: %r' % old[:60])
        text = text.replace(old, new)
    return text


if __name__ == '__main__':
    path = sys.argv[1]
    out = patch(open(path, encoding='utf-8').read())
    compile(out, path, 'exec')
    open(path, 'w', encoding='utf-8').write(out)
    print('patched', path)
