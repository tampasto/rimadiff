import tomllib
from pathlib import Path

from platformdirs import PlatformDirs

from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.user_setup import UserSetup


class ConfigReader(RimadiffCommon):
    DEFAULT_CONFIG = 'default_config.toml'

    def __init__(self):
        self._dirs = PlatformDirs('rimadiff', False)
        self.path = self._dirs.place_config_file('rimadiff.toml')
        self.history_path = None
        self.history_path_from_config = None
        self.api_url = None
        self.setup_names = None
        self.user_setup = None

    def ensure_config(self):
        if not self.path.is_file():
            default_path = Path(__file__).parent / ConfigReader.DEFAULT_CONFIG
            with (default_path.open('rb') as default_config,
                self.path.open('wb') as new_config):
                # Write new default config
                new_config.write(default_config.read())
            self.warning(f'\nWrote new configuration file in\n  {self.path}')

    def read(self):
        toml = None
        try:
            with self.path.open('rb') as fp:
                toml = tomllib.load(fp)
        except Exception as err:
            self.quit_error(err, f'Configuration path: {self.path}')

        self._determine_history_path(toml)
        self.api_url = toml['api_url']
        self.setup_names = list(toml['user-setup'])
        self.user_setup = {
            name: UserSetup(setup, self.history_path)
            for name, setup in toml['user-setup'].items()
            }

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



