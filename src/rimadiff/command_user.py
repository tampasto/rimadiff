from datetime import date

import click

from rimadiff.command_common import COMMON_EPILOG, config_dir_option
from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@click.option(
    '-s', '--user-setup', default='default',
    metavar='NAME', envvar='RIMADIFF_USER_SETUP',
    help='Name of user setup, using "default" if not given'
    )
@config_dir_option
def user(user_setup, config_dir):
    """List information on the users."""
    config = ConfigReader(config_dir)
    config.ensure_config()
    config.read()

    cmd = CommandUser()
    cmd.list_users(user_setup, config)


class CommandUser(RimadiffCommon):
    def list_users(self, setup_name, config):
        counts = latest_snapshot = None

        history_path = config.history_path
        setup = config.get_user_setup(setup_name)
        user_set = set(setup.users) # Config
        user_orig = setup.user_orig.copy()

        if history_path.exists():
            with HistoryManager(history_path) as history:
                counts, latest_snapshot = history.get_info_users()

            # counts: U.name, U.name_original, Count(R.date_ordinal)
            # latest_snapshot: U.name, R2.date_ordinal, R2.time, R2.timezone

            user_set |= (
                {r[0] for r in counts} | {r[0] for r in latest_snapshot})

            # If both database and config aliases, show config aliases
            user_orig |= {r[0]: r[1] for r in counts if r[0] not in user_orig}

        header = ['Name', 'Alias', 'RIMA', 'Snapshots', 'Latest snapshot']
        align = ['left', 'left', 'left', 'right', 'center']
        header_row = [TableCell(t) for t in header]
        table = Table('user', 'info-table', header_row, align)

        tz_set = set()
        if latest_snapshot is not None:
            tz_set = {t[3] for t in latest_snapshot}
        same_tz = (len(tz_set) == 1)
        for row_i, user in enumerate(sorted(user_set)):
            snapshots = latest_date = '-'
            date_ordinal = -1
            if counts is not None:
                count_row = next(r for r in counts if r[0] == user)
                snapshot_row = next(
                    r for r in latest_snapshot if r[0] == user)

                snapshots = count_row[2]
                _, date_ordinal, time, timezone = snapshot_row

                tz_part = ('' if same_tz else f' {timezone}')
                if date_ordinal is not None:
                    latest_date = (
                        f'{date.fromordinal(date_ordinal)} {time}{tz_part}')

            user_original = user_orig[user]
            alias = setup.user_alias.get(user, '-')
            is_rima = ('X' if user == setup.rima else '')
            row_values = [
                (user_original,),
                (alias,),
                (is_rima,),
                (snapshots,),
                (latest_date, date_ordinal),
                ]
            row = [TableCell(*a) for a in row_values]
            table.add_row(row)

        click.echo()
        table.echo()

        tz_info = ''
        if same_tz:
            tz_info = f' Timezone {next(iter(tz_set))}.'
        click.echo(
            f'Aliases and RIMA from user setup "{setup_name}".{tz_info}\n')
