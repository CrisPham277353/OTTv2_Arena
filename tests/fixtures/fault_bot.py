import json
import sys
import time

# Behavior selected by fixture filename, with one reusable source for test cases.
mode = __file__.split('/')[-1].split('\\')[-1].split('.')[0]
for line in sys.stdin:
    r = json.loads(line)
    if mode == 'timeout': time.sleep(2)
    if mode == 'crash': sys.exit(7)
    if mode == 'bad_json':
        print('this is not JSON', flush=True)
        continue
    if mode == 'long_line':
        print('x' * 70000, flush=True)
        continue
    if mode == 'stdout_flood':
        sys.stdout.write('x' * 4000000)
        sys.stdout.flush()
        time.sleep(2)
    if mode == 'stderr_flood':
        sys.stderr.write('x' * 1100000)
        sys.stderr.flush()
        time.sleep(2)
    a = r['observation']['legalActions'][0]
    if mode == 'illegal': a = {'type':'MOVE', 'from':'a1', 'to':'i9'}
    request_id = 'wrong' if mode == 'wrong_id' else r['requestId']
    turn = True if mode == 'bad_turn' else r['turnId']
    print(json.dumps({'type':'action', 'protocolVersion':'1.0', 'requestId':request_id, 'turnId':turn, 'action':a}), flush=True)
