from datetime import date, timedelta

import click

from rimadiff.command_common import (
    COMMON_EPILOG, config_dir_option, history_path_option)
from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.colour_base import ColourBase
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@click.option(
    '-t', '--table', envvar='RIMADIFF_TABLE',
    help='Select table'
    )
@click.option('-f', '--from', 'from_', help='Date of snapshot number')
@click.option('-u', '--until', help='Date or snapshot number')
@config_dir_option
@history_path_option
@click.argument('user', nargs=-1)
@click.pass_context
def history(ctx, table, from_, until, config_dir, history_path, user):
    """
    Show history.

    With no arguments, lists history snapshots. With one or more user
    arguments, prints history table for the users or user aliases
    (case-insensitive).

    For user history, as many snapshots are shown as there is available
    or there is space in the terminal width. The date range can be
    further narrowed with options --from and --to. Left and right column
    show absolute values at the first and last snapshot and intermediary
    columns show the difference compared to earlier snapshot. Choose the
    table type with --table option. Skill levels is default.

    Dates can be in format Y-M-D, M-D. Positive integer means snapshot
    number, negative means "days ago", value "w" means a week ago and
    value "m" means a month ago.
    """
    from_val = _parse_fromuntil(from_, ctx, '--from')
    until_val = _parse_fromuntil(until, ctx, '--until')

    config = ConfigReader(config_dir, history_path)
    config.read()

    cmd = CommandHistory()

    click.echo()
    has_history = cmd.check_history(config)
    if has_history:
        if user:
            cmd.show_user_history(config, user, table, from_val, until_val)
        else:
            cmd.list_snapshots(config)

    config.complain_if_no_config()


def _parse_fromuntil(arg, ctx, opt_name):
    if arg is None:
        return None

    val = None
    try:
        val = int(arg)
    except ValueError:
        if arg == 'w':
            val = date.today() - timedelta(days=7)
        if arg == 'm':
            val = _month_ago_date()
        else:
            parts = arg.split('-')
            try:
                nums = [int(p) for p in parts]
            except ValueError:
                _quit_fromuntil_error(ctx, opt_name, arg)
            else:
                if len(nums) == 3:
                    val = date(*nums)
                if len(nums) == 2:
                    val = date.today().replace(month=nums[0], day=nums[1])
                else:
                    _quit_fromuntil_error(ctx, opt_name, arg)
    else:
        if val < 0:
            val = date.today() - timedelta(days=abs(val))
    return val


def _month_ago_date():
    today = date.today()
    year, month = today.year, today.month-1
    if month == 0:
        month = 12
        year -= 1
    return today.replace(year=year, month=month)


def _quit_fromuntil_error(ctx, opt_name, arg):
    click.echo(ctx.get_usage() + f'\n\nError: Bad {opt_name} value: {arg!r}')
    ctx.exit(2)


class CommandHistory(ColourBase):
    def check_history(self, config):
        if not config.history_path.exists():
            self.warning(
                'History database does not exist.\n\n'
                f'Path: {config.history_path}'
                )
            return False
        return True

    def list_snapshots(self, config):
        snapshots = None
        history_path = config.history_path
        with HistoryManager(history_path) as history:
            snapshots = history.get_history_snapshots()

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

        table.echo()

    def show_user_history(self, config, user_list, table, from_val, until_val):
        click.echo('Not implemented\n')
        return

        with HistoryManager(config.history_path) as history:
            user_ids = self._get_user_ids(user_list, history)
        if user_ids is None:
            return

    def _get_user_ids(self, arg_user_list, history):
        user_id_dict = history.get_user_id_dict()
        user_ids = []
        for user_arg in arg_user_list:
            name = user_arg.strip().lower()
        return user_ids
