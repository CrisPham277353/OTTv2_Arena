"""Manifests identify implementations; the registry never imports game rules."""
import importlib
import json
from pathlib import Path
from arena.core.plugin import GamePlugin


class PluginRegistry:
    def __init__(self):
        self.entries: dict[tuple[str, str], tuple[dict, GamePlugin]] = {}

    def register(self, manifest: dict, plugin: GamePlugin):
        if (manifest['pluginApi'] != '1.0' or manifest['players'] != 2
                or manifest['turnMode'] != 'alternating'
                or manifest['resultMode'] != 'winner_only'):
            raise ValueError('Only plugin API 1.0, two-player alternating winner-only games are supported')
        key = (manifest['gameId'], manifest['gameVersion'])
        if key in self.entries:
            raise ValueError(f'Duplicate plugin: {key}')
        self.entries[key] = (manifest, plugin)

    def load(self, path: Path):
        manifest = json.loads(path.read_text(encoding='utf-8'))
        module, name = manifest['implementation'].split(':')
        self.register(manifest, getattr(importlib.import_module(module), name)())

    def get(self, game_id: str, version: str | None = None):
        matches = [entry for (gid, ver), entry in self.entries.items()
                   if gid == game_id and (version is None or ver == version)]
        if version is None and len(matches) > 1:
            defaults = [entry for entry in matches if entry[0].get('isDefault') is True]
            if len(defaults) == 1:
                return defaults[0]
        if len(matches) != 1:
            raise KeyError(f'Unknown or ambiguous game version: {game_id}@{version}')
        return matches[0]

    def catalog(self):
        return [manifest.copy() for manifest, _ in self.entries.values()]
