"""Composition root discovers trusted manifests; core remains game independent."""
from pathlib import Path
from arena.core.bot_runner import BotCatalog
from arena.core.registry import PluginRegistry

ROOT = Path(__file__).resolve().parent.parent


def build_registry():
    registry = PluginRegistry()
    for manifest in sorted((ROOT / 'arena' / 'games').glob('*/manifest*.json')):
        registry.load(manifest)
    return registry


def build_bots():
    return BotCatalog(ROOT / 'bots')
