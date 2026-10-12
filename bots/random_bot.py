from bot_sdk import run

if __name__ == '__main__':
    run(lambda obs, rng: rng.choice(obs['legalActions']))
