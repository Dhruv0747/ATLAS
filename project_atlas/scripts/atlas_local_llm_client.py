#!/usr/bin/env python3
"""Local text-only client. No ROS, robot commands, cloud requests or audio capture."""
import argparse
import json
import os
import socket

SOCKET_PATH = os.path.expanduser('~/.local/state/atlas-llm/assistant.sock')
MAX_MESSAGE = 16384


def request_local(text=None, context=None, history=None, timeout=28):
    body = {'op': 'status'} if text is None else {
        'op': 'ask', 'text': text, 'context': context or {}, 'history': history or []}
    raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode() + b'\n'
    if len(raw) > MAX_MESSAGE:
        raise ValueError('Local assistant request is too large')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(SOCKET_PATH)
        client.sendall(raw)
        with client.makefile('rb') as stream:
            reply = stream.readline(MAX_MESSAGE + 1)
    if len(reply) > MAX_MESSAGE or not reply.endswith(b'\n'):
        raise ValueError('Invalid local assistant response')
    result = json.loads(reply)
    if not isinstance(result, dict):
        raise ValueError('Invalid local assistant response')
    if not result.get('ok'):
        raise RuntimeError(result.get('reason', 'Local assistant unavailable'))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ask', help='Text question; omit for status. Does not speak or move ATLAS.')
    args = parser.parse_args()
    try:
        print(json.dumps(request_local(args.ask), ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
