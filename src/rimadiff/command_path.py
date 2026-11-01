from datetime import datetime

import click

from rimadiff.command_common import COMMON_EPILOG, config_dir_option
from rimadiff.config_reader import ConfigReader
from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@config_dir_option
def path(config_dir):
    """List paths used by the script."""
    config = ConfigReader(config_dir)
    config.ensure_config()
    config.read()

    cmd = CommandPath()
    cmd.list_paths(config)


class CommandPath(RimadiffCommon):
    def list_paths(self, config):
        paths = [
            ['General config', config.path, '', False],
            ['Colour config', config.colour_path, '', False],
            ['History database', config.history_path, '',
                config.history_path_from_config]
            ]

        # List path information
        align = ['left', 'left', 'right', 'center']
        header = ['Name', 'Source', 'Size', 'Modified']
        time_fmt = '%Y-%m-%d %H:%M'

        header_row = [TableCell(t) for t in header]
        info_table = Table('path-info', 'info-table', header_row, align)
        errs = []
        for entry in paths:
            from_config = entry[3]
            source = ('Config' if from_config else '-')
            size = '<err>'
            modified = '<err>'
            path = entry[1]
            try:
                st = path.stat()
            except FileNotFoundError:
                size = modified = '-'
                entry[2] = ' (does not exist)'
            except OSError as err:
                errs.append(str(err))
            else:
                size = self._size_format(st.st_size)
                mod_dt = datetime.fromtimestamp(st.st_mtime)
                modified = mod_dt.strftime(time_fmt)

            name = entry[0]
            row_values = [name, source, size, modified]
            row = [TableCell(t) for t in row_values]
            info_table.add_row(row)

        click.echo()
        if errs:
            self.error('\n'.join(errs))
        info_table.echo()

        # List actual paths
        align = ['left', 'left']
        header = ['Name', 'Path']

        header_row = [TableCell(t) for t in header]
        path_table = Table('path', 'info-table', header_row, align)
        for name, path, exist, _ in paths:
            row = [TableCell(v) for v in (name, f'{path}{exist}')]
            path_table.add_row(row)
        path_table.echo()

        tz = datetime.now().astimezone().strftime('%z')
        click.echo(f'Timezone {tz}.\n')

    def _size_format(self, size):
        if size/10 > 1024**3:
            return f'{size//1024**3}G'
        elif size/10 > 1024**2:
            return f'{size//1024**2}M'
        elif size/10 > 1024:
            return f'{size//1024}k'
        return f'{size}'
