"""Bot-only helpers. This module does not import arena or read engine state."""
import json
import os
import random
import sys


def distance(a, b):
    return max(abs(ord(a[0]) - ord(b[0])), abs(int(a[1]) - int(b[1])))


def run(choose):
    rng = random.Random(int(os.environ.get('ARENA_BOT_SEED', '42')))
    for line in sys.stdin:
        request = json.loads(line)
        action = choose(request['observation'], rng)
        print(json.dumps({'type': 'action', 'protocolVersion': '1.0',
                          'requestId': request['requestId'], 'turnId': request['turnId'],
                          'action': action}), flush=True)
