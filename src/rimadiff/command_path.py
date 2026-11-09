import os
from datetime import datetime
from pathlib import Path

import click
import click.core

from rimadiff.colour_base import ColourBase
from rimadiff.command_common import (
    COMMON_EPILOG, config_dir_option, history_path_option)
from rimadiff.config_reader import ConfigReader
from rimadiff.format_base import FormatBase
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@config_dir_option
@history_path_option
@click.pass_context
def path(ctx, config_dir, history_path):
    """List paths used by the script."""
    config = ConfigReader(config_dir, history_path)
    config.read()

    cmd = CommandPath()
    common_options = {'config_dir': config_dir, 'history_path': history_path}
    cmd.list_paths(ctx, config, common_options)


class CommandPath(ColourBase, FormatBase):
    def list_paths(self, ctx, config, common_options):
        source_names = [
            ctx.get_parameter_source(n).name
            for n in ('config_dir', 'history_path')
            ]
        name_replace = {
            'COMMANDLINE': 'Command line', 'DEFAULT': 'OS directory'}
        def name_map(n):
            if n in name_replace:
                return name_replace[n]
            return n.replace('_', ' ').capitalize()
        config_source, history_source = map(name_map, source_names)

        paths = []
        for name, path in config.paths.items():
            name_header = f'{name} config'
            paths.append((name_header, path, config_source))

        paths.append((
            'History database', config.history_path, history_source))

        # List path information
        align = ['left', 'left', 'right', 'left']
        header = ['Name', 'Source', 'Size', 'Modified']

        header_row = [TableCell(t) for t in header]
        info_table = Table('path-info', 'info-table', header_row, align)
        errs = []
        for name_header, path, source in paths:
            try:
                st = path.stat()
            except FileNotFoundError:
                size = modified = '-'
            except OSError as err:
                size = modified = '<err>'
                errs.append(str(err))
            else:
                size = self.format_size(st.st_size)
                mod_dt = datetime.fromtimestamp(st.st_mtime)
                modified = self.format_time(mod_dt)

            row_values = [name_header, source, size, modified]
            info_table.add_row(map(TableCell, row_values))

        click.echo()
        if errs:
            self.error('\n'.join(errs))
        info_table.echo()

        # List actual paths
        align = ['left', 'left']
        header = ['Name', 'Path']

        header_row = [TableCell(t) for t in header]
        path_table = Table('path', 'info-table', header_row, align)
        for header_name, path, _ in paths:
            row_values = [header_name, path]
            path_table.add_row(map(TableCell, row_values))
        path_table.echo()

        tz = datetime.now().astimezone().strftime('%z')
        click.echo(f'Timezone {tz}.\n')

        config.complain_if_no_config()
