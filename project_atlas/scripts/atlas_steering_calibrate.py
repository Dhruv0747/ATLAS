#!/usr/bin/env python3
"""Retired direct-serial utility. Steering belongs to the guarded motor owner."""

import argparse
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_known_args()
    parser.error(
        'This legacy tool bypassed motor ownership and reversed the current '
        'front/rear PWM mapping. Use the existing steering calibration page '
        'and motor-owner lease after supervised test approval. No serial '
        'port opened; no motor or servo command issued.'
    )


if __name__ == "__main__":
    main()
