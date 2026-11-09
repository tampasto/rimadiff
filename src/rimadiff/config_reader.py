import tomllib
from pathlib import Path

import click
from platformdirs import PlatformDirs

from rimadiff.api_url import APIUrl
from rimadiff.categories import api_categories
from rimadiff.category import Category
from rimadiff.colour_base import ColourBase
from rimadiff.format_base import FormatBase
from rimadiff.user_setup import UserSetup


class ConfigReader(ColourBase):
    CONFIG_FILES = {
        'General': 'rimadiff.toml',
        'Colour': 'colour.toml',
        'API URL': 'api_url.toml'
        }
    HISTORY_FILE = 'history.db'
    DEFAULT_DIR_PATH = 'config_default'
    COMPLAIN_NO_CONFIG = (
        'Configuration files do not exist!\n\n'
        'Initialize them explicitly with command "rimadiff '
        'init-config" or run the base command "rimadiff" and use the '
        'default configuration to get a demo.\n'
        )

    ERROR_PATH = '{} configuration path:\n  {}'
    NEW_CONFIG_INFO = 'Wrote a new {} configuration file in:\n  {}'

    def __init__(self, config_dir=None, history_path=None):
        dirs = PlatformDirs('rimadiff', False)
        self.paths = self._determine_config_paths(dirs, config_dir)
        self.history_path = self._determine_history_path(dirs, history_path)
        self._no_config = True

        # General config
        self.user_setup: dict[str, UserSetup] | None = None
        self.colour_scheme: str | None = None
        # time_format reassigns FormatBase.time_format (str)

        # Colour config reassigns ColourBase.scheme (dict)

        # API URL config
        self.api_url: dict[str, APIUrl] | None = None
        self._correct_api_names = None

        self._ensured_files = None

    def _determine_config_paths(self, dirs, config_dir):
        paths = {}
        if isinstance(config_dir, Path):
            config_dir.mkdir(parents=True, exist_ok=True)
            for name, filename in ConfigReader.CONFIG_FILES.items():
                paths[name] = config_dir / filename
        else:
            for name, filename in ConfigReader.CONFIG_FILES.items():
                paths[name] = dirs.place_config_file(filename)
        return paths

    def _determine_history_path(self, dirs, history_path):
        if isinstance(history_path, Path):
            history_path.parent.mkdir(parents=True, exist_ok=True)
            path = history_path
        else:
            path = dirs.place_data_file(ConfigReader.HISTORY_FILE)
        return path

    def ensure_config(self):
        self._ensured_files = []
        for name, path in self.paths.items():
            if not path.is_file():
                file_tuple = self._write_default_config(name, path)
                if file_tuple:
                    self._ensured_files.append(file_tuple)

    def complain_if_no_config(self):
        if self._no_config:
            click.echo(ConfigReader.COMPLAIN_NO_CONFIG)

    def _write_default_config(self, name, dest):
        default_path = Path(__file__).parent / ConfigReader.DEFAULT_DIR_PATH
        source_path = default_path / dest.name
        try:
            with (source_path.open('rb') as default_config,
                dest.open('wb') as new_config):
                # Write new default config
                new_config.write(default_config.read())
        except OSError:
            self.quit_config_error(err, name)
        name_lc = self._config_name_lower(name)
        return name_lc, dest

    def read(self):
        # Ordered as ConfigReader.CONFIG_FILES
        readers = (
            (self._read_general_config, True),
            (self._read_colour_config, False),
            (self._read_api_url_config, True)
            )

        for (name, path), (read, required) in zip(self.paths.items(), readers):
            toml = self._read_file(name, required)
            if toml is not None:
                read(name, toml)
                if name == 'General':
                    self._no_config = False

        if self._ensured_files:
            click.echo()
            for file_tuple in self._ensured_files:
                msg = ConfigReader.NEW_CONFIG_INFO.format(*file_tuple)
                self.info(msg)

        if self.user_setup:
            for setup_name, setup in self.user_setup.items():
                setup.validate_api_names(setup_name, self._correct_api_names)

    def _read_general_config(self, config_name, toml):
        keys = ('colour_scheme', 'time_format', 'user-setup')
        values = self._read_keys(config_name, toml, keys)
        colour_scheme, time_format, user_setup = values
        self.user_setup = {
            name: UserSetup(setup, self.paths[config_name])
            for name, setup in user_setup.items()
            }
        self.colour_scheme = colour_scheme or 'default'
        if time_format:
            FormatBase.time_format = time_format

    def _read_colour_config(self, config_name, toml):
        scheme = toml.get(self.colour_scheme)
        if not isinstance(scheme, dict):
            self.warning(f'No such colour scheme {self.colour_scheme!r}.')
        else:
            ColourBase.scheme = scheme

    def _read_api_url_config(self, config_name, toml):
        keys = ('url', 'api')
        values = self._read_keys(config_name, toml, keys)
        url_dict, api_dict = values

        self.api_url = {}
        correct_names = []
        for name, defs in api_dict.items():
            url_name = self._get_required(
                defs, 'url', config_name, f'api.{name}')
            url = url_dict[url_name]
            if 'model' in defs:
                url = url.replace('{model}', defs['model'])
            display = self._get_required(
                defs, 'display', config_name, f'api.{name}')
            self.api_url[name] = APIUrl(url, display)

            cat = Category(name, display)
            api_categories.append(cat)
            correct_names.append(name)
        self._correct_api_names = correct_names

    def _get_required(self, subdict, key, config_name, pos):
        value = subdict.get(key)
        if not value:
            msg = f'Missing required key {key!r} in configuration at {pos!r}.'
            self.quit_config_error(msg, config_name)
        return value

    def _read_keys(self, config_name, toml, keys):
        values = [toml.get(k) for k in keys]
        unrecognized = set(toml.keys()) - set(keys)
        if unrecognized:
            msg = (
                f'Unrecognized keys in configuration file:\n  '
                + sorted(unrecognized)
                )
            self.quit_config_error(msg, config_name)
        return tuple(values)

    def check_user_setup(self, name):
        valid_names = list(self.user_setup.keys())
        if self.user_setup.get(name) is None:
            return False, valid_names
        return True, valid_names

    def _read_file(self, config_name, required=True):
        path = self.paths[config_name]
        toml = None
        try:
            with path.open('rb') as fp:
                toml = tomllib.load(fp)
        except FileNotFoundError as err:
            pass
        except OSError as err:
            if required:
                self.quit_config_error(err, config_name)
            else:
                self.warning(
                    f'Could not open {config_name} configuration.\n'
                    f'{type(err).__name__}: {err}'
                    f'\nPath: {path}'
                    )
        return toml

    def _config_name_lower(self, name):
        if name == 'API URL':
            return name
        return name.lower()

    def quit_config_error(self, msg, config_name):
        extra = ConfigReader.ERROR_PATH.format(
            config_name, self.paths[config_name])
        self.quit_error(msg, extra)
