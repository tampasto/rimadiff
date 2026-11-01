from datetime import date

import click

from rimadiff.command_common import COMMON_EPILOG, config_dir_option
from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.colour_base import ColourBase
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@config_dir_option
def history(config_dir):
    """
    List history snapshots.

    \b
    Environment variables:
    RIMADIFF_CONFIG_DIR  Default value for --config-dir
    """
    config = ConfigReader(config_dir)
    config.ensure_config()
    config.read()

    cmd = CommandHistory()
    cmd.list_history(config)


class CommandHistory(ColourBase):
    def list_history(self, config):
        snapshots = None
        history_path = config.history_path
        if history_path.exists():
            with HistoryManager(history_path) as history:
                snapshots = history.get_history_snapshots()
        else:
            self.warning(
                '\nHistory database does not exist.\n\n'
                f'Path: {history_path}'
                )
            return

        header = ['Num', 'Date', 'Time', 'Timezone']
        align = ['right', 'center', 'left', 'left']
        header_row = [TableCell(t) for t in header]
        table = Table('history', 'info-table', header_row, align)

        for snapshot_i, (date_ordinal, time_list) in enumerate(snapshots):
            date_obj = date.fromordinal(date_ordinal)
            date_str = f'{date_obj}'
            num = len(snapshots) - snapshot_i
            time = ', '.join(t[0] for t in time_list)
            tz = ', '.join({t[1]: 0 for t in time_list})

            row_values = [(num,), (date_str, date_ordinal), (time,), (tz,)]
            row = [TableCell(*a) for a in row_values]
            table.add_row(row)

        click.echo()
        table.echo()
