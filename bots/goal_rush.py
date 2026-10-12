from bot_sdk import run, distance


def choose(obs, rng):
    pieces = {p['at']: p for p in obs['pieces']}
    beats = {'D': 'K', 'K': 'L', 'L': 'D'}
    def score(a):
        kind = pieces[a['from']]['kind']
        danger = sum(p['side'] != obs['side'] and p['at'] != a['to']
                     and beats[p['kind']] == kind and distance(p['at'], a['to']) == 1
                     for p in obs['pieces'])
        remaining = distance(a['to'], obs['target'])
        # Landing on the goal ends the game immediately; otherwise penalize risk.
        return (remaining + 2 * danger if remaining else -100, remaining, a['from'], a['to'])
    return min(obs['legalActions'], key=score)


if __name__ == '__main__':
    run(choose)
