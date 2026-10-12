"""Copy to a new .py file and register its id/script in bots/manifest.json."""
from bot_sdk import run


def choose(observation, rng):
    return observation['legalActions'][0]


if __name__ == '__main__':
    run(choose)
