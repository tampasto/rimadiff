from collections import defaultdict
from datetime import date

import click

from rimadiff.categories import api_categories
from rimadiff.colour_base import ColourBase
from rimadiff.command_common import (
    COMMON_EPILOG, config_dir_option, history_path_option)
from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


@click.command(epilog=COMMON_EPILOG)
@click.option(
    '-s', '--user-setup',
    metavar='NAME',
    help='Show only users for a specific user setup'
    )
@config_dir_option
@history_path_option
def user(user_setup, config_dir, history_path):
    """List information on the users."""
    config = ConfigReader(config_dir, history_path)
    config.read()

    cmd = CommandUser()
    cmd.list_users(user_setup, config)
    config.complain_if_no_config()


class CommandUser(ColourBase):
    def list_users(self, setup_name, config):
        click.echo()
        setup = None
        if setup_name and config.user_setup is None:
            click.echo('Cannot show user setup as there is no configuration.')
            return
        if setup_name and config.user_setup is not None:
            setup = config.user_setup.get(setup_name)
            if not setup:
                self.warning('No such user setup: {setup_name!r}.')
                return
        history_exists = (config.history_path and config.history_path.exists())
        if not history_exists and config.user_setup is None:
            click.echo('History database is missing.\n')
            return

        user_set = set()
        user_display_dict = {}
        in_setups = None
        setup_aliases = None
        user_rimas = None
        if setup:
            user_set = set(setup.users) # Config
            user_display_dict = setup.user_display.copy()
        elif config.user_setup is not None:
            user_set = set()
            user_display_dict = {}
            in_setups = defaultdict(list)
            setup_aliases = defaultdict(list)
            user_rimas = defaultdict(list)
            us_list = list(config.user_setup.items())
            us_list.sort(key=lambda t: ((t[0] != 'default'), t[0]))
            for us_name, us in us_list:
                for user in us.users:
                    user_set.add(user)
                    in_setups[user].append(us_name)
                    alias = us.user_alias.get(user) or '-'
                    setup_aliases[user].append(alias)
                    user_rimas[user].append('X' if user == us.rima else '-')
                user_display_dict |= us.user_display

        counts = latest_snapshot = None
        history_path = config.history_path
        if history_path and history_path.exists():
            with HistoryManager(history_path) as history:
                history.ensure_api_category_ids()
                counts, latest_snapshot = history.get_info_users()

            if not setup:
                user_set |= {r.user for r in counts}
                user_set |= {r.user for r in latest_snapshot}

            # If both database and config aliases, show config aliases
            user_display_dict |= {
                r.user: r.user_display
                for r in counts
                if r.user not in user_display_dict
                }
        for user in user_set:
            if len(in_setups[user]) == 0:
                in_setups[user].append('<only history>')

        header = [
            'Name', 'Alias', 'RIMA', 'Snapshots', 'Latest snapshot',
            'Latest API'
            ]
        align = ['left', 'left', 'left', 'right', 'left', 'left']
        if in_setups is not None:
            header.insert(1, 'Setup')
            align.insert(1, 'left')

        header_row = map(TableCell, header)
        table = Table('user', 'info-table', header_row, align)

        tz_set = set()
        if latest_snapshot is not None:
            tz_set = {r.timezone for r in latest_snapshot}
        same_tz = (len(tz_set) == 1)

        def user_sort_key(user):
            if setup:
                return user
            elif in_setups is not None:
                setup_name = in_setups[user][0]
                return ((setup_name != 'default'), setup_name, user)
            return user

        users = sorted(user_set, key=user_sort_key)
        for row_i, user in enumerate(users):
            snapshot_count = latest_date = api_display = '-'
            date_ordinal = -1
            if counts is not None:
                count_row = next((r for r in counts if r.user == user), None)
                if count_row:
                    snapshot_count = count_row.snapshot_count

                    ss = next(
                        r for r in latest_snapshot if r.user == user)
                    date_ordinal = ss.date_ordinal

                    tz_part = ('' if same_tz else f' {ss.timezone}')
                    if date_ordinal is not None:
                        latest_date = (
                            f'{date.fromordinal(date_ordinal)} '
                            f'{ss.time}{tz_part}'
                            )

                    api_cat = next(
                        (c for c in api_categories if c.id == ss.api_cat_id),
                        None
                        )
                    if api_cat:
                        api_display = api_cat.display

            user_display = user_display_dict[user]
            alias = rima_text = '-'
            if setup:
                alias = setup.user_alias.get(user, '-')
                rima_text = ('X' if user == setup.rima else '-')
            elif setup_aliases is not None:
                alias = ', '.join(setup_aliases[user])
                rima_text = ', '.join(user_rimas[user])
            row_values = [
                (user_display,),
                (alias,),
                (rima_text,),
                (snapshot_count,),
                (latest_date, date_ordinal),
                (api_display,),
                ]
            if in_setups is not None:
                setup_str = ', '.join(in_setups[user])
                row_values.insert(1, (setup_str,))
            row = [TableCell(*a) for a in row_values]
            table.add_row(row)

        table.echo()

        if same_tz:
            click.echo('Timezone ' + next(iter(tz_set)) + '.\n')
