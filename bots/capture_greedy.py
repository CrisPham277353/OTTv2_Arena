from bot_sdk import run, distance


def choose(obs, rng):
    enemies = {p['at'] for p in obs['pieces'] if p['side'] != obs['side']}
    return min(obs['legalActions'], key=lambda a: (a['to'] not in enemies, distance(a['to'], obs['target']), a['from'], a['to']))


if __name__ == '__main__':
    run(choose)
