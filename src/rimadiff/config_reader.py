import tomllib
from pathlib import Path

import click
from platformdirs import PlatformDirs

from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.user_setup import UserSetup


class ConfigReader(RimadiffCommon):
    DEFAULT_CONFIG = 'default_config.toml'
    DEFAULT_COLOUR_CONFIG = 'config_default_colour.toml'

    def __init__(self):
        self._dirs = PlatformDirs('rimadiff', False)
        self.path = self._dirs.place_config_file('rimadiff.toml')
        self.colour_path = self._dirs.place_config_file('colour.toml')
        self.history_path = None
        self.history_path_from_config = None
        self.api_url = None
        self.user_setup = None
        self.colour_scheme = None

    def ensure_config(self):
        if not self.path.is_file():
            self._write_default_config(
                'general', ConfigReader.DEFAULT_CONFIG, self.path)

        if not self.colour_path.is_file():
            self._write_default_config(
                'colour', ConfigReader.DEFAULT_COLOUR_CONFIG, self.colour_path)

    def _write_default_config(self, name, filename, dest):
        project_root = Path(__file__).parent
        source_path = project_root / filename
        with (source_path.open('rb') as default_config,
            dest.open('wb') as new_config):
            # Write new default config
            new_config.write(default_config.read())
        click.echo(f'\nWrote a new {name} configuration file in\n  {dest}')

    def read(self):
        # General config
        toml = None
        try:
            with self.path.open('rb') as fp:
                toml = tomllib.load(fp)
        except Exception as err:
            self.quit_error(err, f'Configuration path: {self.path}')

        self._determine_history_path(toml)
        self.api_url = toml['api_url']
        self.user_setup = {
            name: UserSetup(setup, self.history_path)
            for name, setup in toml['user-setup'].items()
            }
        self.colour_scheme = toml.get('colour_scheme') or 'default'

        # Colour config
        toml = None
        try:
            with self.colour_path.open('rb') as fp:
                toml = tomllib.load(fp)
        except Exception as err:
            self.warning(
                f'Could not open colour configuration.\n'
                f'{type(err).__name__}: {err}'
                f'\nPath: {self.colour_path}'
                )
        else:
            scheme = toml.get(self.colour_scheme)
            if not isinstance(scheme, dict):
                self.warning(f'No such colour scheme {self.colour_scheme!r}.')
            else:
                RimadiffCommon.colour_scheme = scheme

    def check_user_setup(self, name):
        valid_names = list(self.user_setup.keys())
        if self.user_setup.get(name) is None:
            return False, valid_names
        return True, valid_names

    def _determine_history_path(self, toml):
        history_path = None
        config_path = toml.get('history_path')
        from_config = False
        if config_path:
            history_path = Path(config_path).expanduser().resolve()
            from_config = True
        else:
            history_path = self._dirs.place_data_file('history.db')
        self.history_path = history_path
        self.history_path_from_config = from_config

    def get_user_setup(self, setup_name):
        return self.user_setup.get(setup_name)



