import click

from rimadiff.command_common import (
    COMMON_EPILOG, config_dir_option, history_path_option)
from rimadiff.config_reader import ConfigReader


@click.command(epilog=COMMON_EPILOG)
@config_dir_option
@history_path_option
def init_config(config_dir, history_path):
    """List paths used by the script."""
    config = ConfigReader(config_dir, history_path)
    config.ensure_config()
    config.read()
