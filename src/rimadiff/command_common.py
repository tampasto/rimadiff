from pathlib import Path

import click


COMMON_EPILOG="""\b
    Environment variables:
      RIMADIFF_CONFIG_DIR    Default value for --config-dir
      RIMADIFF_HISTORY_PATH  Default value for --history-path
    """

config_dir_option = click.option(
    '--config-dir',
    metavar='PATH', envvar='RIMADIFF_CONFIG_DIR',
    type=click.Path(
        file_okay=False, writable=True, resolve_path=True, path_type=Path),
    help='Path to the configuration directory'
    )

history_path_option = click.option(
    '--history-path',
    metavar='PATH', envvar='RIMADIFF_HISTORY_PATH',
    type=click.Path(
        dir_okay=False, writable=True, resolve_path=True, path_type=Path),
    help='Path to the history database file'
    )
