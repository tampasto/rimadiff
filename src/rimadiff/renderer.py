import math
import shutil
from collections import namedtuple
from datetime import date, datetime
from numbers import Number

import click

from rimadiff.api_manager import APIManager
from rimadiff.api_response import APIResponse
from rimadiff.categories import data_categories
from rimadiff.colour_base import ColourBase
from rimadiff.format_base import FormatBase
from rimadiff.history_manager import HistoryManager
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


class Renderer(ColourBase, FormatBase):
    def __init__(self, config):
        self.config = config

        self._force_download = False

    def print_tables(self, setup_name, force_download, table_names):
        setup = self.config.user_setup.get(setup_name)

        self._force_download = force_download

        self._validate_rima(setup, table_names)

        err = None
        now = datetime.now().astimezone()
        today_ordinal = now.toordinal()

        history_path = self.config.history_path
        users_rima_first = sorted(
            setup.users, key=lambda u: (u != setup.rima, u))

        clean_table_names = [n.removesuffix('-diff') for n in table_names]

        with (HistoryManager(history_path) as history,
            APIManager(self.config.api_url) as api):

            history.ensure_label_data_category_ids()
            history.ensure_api_category_ids(setup.api_names)

            data_cat_ids = [
                c.id for c in data_categories
                if c.table_name in clean_table_names
                ]
            from rimadiff.categories import api_categories
            api_ids = [c.id for c in api_categories]

            # Source data from database and API
            user_id_dict = history.get_user_id_dict()
            cat_data, user_history_time, user_api_id, should_vacuum = (
                self._source_user_data(
                    history, api, now, setup, data_cat_ids, user_id_dict
                ))

            label_dict, label_pos_dict = history.get_label_dict(
                users_rima_first, today_ordinal)

            api_results = api.get_results()

        click.echo()
        api_results.echo_success(setup)

        tables = []
        for name in table_names:
            table_orig_name = name
            table_name = name
            is_diff = False
            if name.endswith('-diff'):
                table_name = name.removesuffix('-diff')
                is_diff = True
            table = self._generate_table(
                table_name, table_orig_name, is_diff, setup, cat_data,
                user_api_id, label_dict, label_pos_dict, user_id_dict,
                today_ordinal
                )
            tables.append(table)

        if len(user_history_time):
            fetch_text = 'Fetched at'
            time_set = set(user_history_time.values())
            if len(time_set) == 1:
                time, timezone = next(iter(user_history_time.values()))
                fetch_text += f' {time} {timezone}'
            else:
                time_order = sorted(time_set)
                tz_set = {t[1] for t in time_set}
                if len(tz_set) == 1:
                    fetch_text += f' ({next(iter(tz_set))})'
                for time_tuple in time_order:
                    time, tz = time_tuple
                    tz_str = ('' if len(tz_set) == 1 else f' {tz}')
                    users = [
                        u for u, t in user_history_time.items()
                        if t == time_tuple
                        ]
                    fetch_text += (
                        f'\n  {time}{tz_str} '
                        + ', '.join(setup.user_display[u] for u in users)
                        )
            click.echo(fetch_text + '\n')

        term_cols, _ = shutil.get_terminal_size()
        self._echo_tables(tables, term_cols)

        ColourBase.print_warnings()
        api_results.echo_errors(setup)

        if should_vacuum:
            msg = 'Compacting history database...'
            msg = msg[:term_cols]
            click.echo(msg, nl=False)
            with HistoryManager(history_path) as history:
                history.vacuum()
            click.echo('\r' + ' ' * len(msg))
        else:
            click.echo()

    def _validate_rima(self, setup, table_names):
        no_rima = not setup.rima
        invalid_rima = setup.rima not in setup.users
        if no_rima or invalid_rima:
            # Complain about RIMA
            prolog = ''
            has_diff_tables = any(n.endswith('-diff') for n in table_names)
            if has_diff_tables:
                prolog = 'Cannot calculate differences, '
            epilog = ('set' if no_rima else f'a user ({setup.rima_display})')
            if has_diff_tables or (invalid_rima and not no_rima):
                self.warning(f'{prolog}RIMA is not {epilog}.')
                for i in range(len(table_names)):
                    table_names[i] = table_names[i].removesuffix('-diff')

    def _source_user_data(
        self, history, api, now, setup, data_cat_ids, user_id_dict
    ):
        # cat_data[data_category_id][user_id][label] = value
        cat_data = {n: {} for n in data_cat_ids}

        today_ordinal = now.toordinal()
        now_time = now.strftime('%H:%M')
        now_timezone = now.strftime('%z')
        time_tuple = today_ordinal, now_time, now_timezone

        db_users = []
        new_users = []
        unique_users = sorted(
            set(setup.users), key=lambda u: setup.users.index(u))

        for user in unique_users:
            if user in user_id_dict:
                id_ = user_id_dict[user]
                db_users.append((id_, user))
            else:
                new_users.append(user)

        # Read data for today from history database
        # today_db_user_data [user_id] [data_category_id] [label] = value
        # user_history_time [user] = (time, timezone)
        today_db_user_data = {}
        user_history_time = {}
        user_api_id = {}
        if not self._force_download:
            user_ids = [t[0] for t in db_users]

            today_db_user_data = history.read_data(
                today_ordinal, user_ids, data_cat_ids)
            user_history_time = history.read_data_time(today_ordinal, user_ids)
            user_api_id = history.get_user_api_id(today_ordinal, user_ids)

        sourced: list[APIResponse] = []
        ctx = history, api # Context managers

        for user_id, user in db_users:
            user_tuple = user, user_id, setup
            db_data = today_db_user_data.get(user_id)
            self._source_existing_user(db_data, user_tuple, ctx, sourced)

        for user in new_users:
            # Assigns new users to user_id_dict
            self._source_new_user(
                user, setup, today_ordinal, ctx, sourced, user_id_dict)

        # Add only requested table categories to cat_data
        for resp in sourced:
            if isinstance(resp, APIResponse):
                data, user_id = resp.data, resp.user_id
                user_api_id[user_id] = resp.api_id
            else:
                # From history
                data, user_id = resp
            for data_cat_id in data_cat_ids:
                cat_data[data_cat_id][user_id] = data[data_cat_id]

        # Write new data to database
        should_vacuum = False
        downloaded = [r for r in sourced if isinstance(r, APIResponse)]
        if downloaded:
            should_vacuum = history.write_data(time_tuple, downloaded)

        return cat_data, user_history_time, user_api_id, should_vacuum

    def _source_existing_user(self, db_data, user_tuple, ctx, sourced):
        user, user_id, setup = user_tuple
        history, api = ctx

        user_display = setup.user_display[user]
        history.update_user_display(user_id, user_display)

        labels = None
        if db_data:
            resp = (db_data, user_id)
        else:
            api_name = setup.get_user_api_name(user)
            resp = api.download_data(user, setup, api_name)
            if not resp:
                return
            resp.user_id = user_id

        sourced.append(resp)

    def _source_new_user(
        self, user, setup, today_ordinal, ctx, sourced, user_id_dict
    ):
        history, api = ctx

        api_name = setup.get_user_api_name(user)
        resp = api.download_data(user, setup, api_name)
        if not resp:
            return

        user_display = setup.user_display[user]
        resp.user_id = history.add_user(user, user_display, today_ordinal)
        user_id_dict[user] = resp.user_id

        sourced.append(resp)

    def _generate_table(
        self, table_name, table_orig_name, is_diff, setup, cat_data,
        user_api_id, label_dict, label_pos_dict, user_id_dict,
        today_ordinal
    ):
        # cat_data   [data_category_id] [user_id] [label] = value

        # label_dict [label_category_id] [label] = display
        #                                \ Ordered on position

        cat = next(
            c for c in data_categories
            if c.table_name == table_name
            )
        lab_cat_id = cat.label_category.id

        user_data = cat_data[cat.id]
        label_display = label_dict[lab_cat_id]
        label_position = label_pos_dict[lab_cat_id]
        # user_data      [user_id] [label] = value
        # label_display            [label] = display
        # label_position           [label] = position
        is_rank = ('-rank' in table_name)

        label_set = set()
        for lab_dict in user_data.values():
            label_set |= set(lab_dict)
        label_names = sorted(label_set, key=lambda l: label_position[l])

        rima_col_i = -1
        rima_api_id = -1
        user_headers = []
        for user_i, user in enumerate(setup.users):
            if user == setup.rima:
                # Nayta dorkalle RIMA
                header = 'RIMA'
                rima_col_i = user_i + 1
                user_id = user_id_dict.get(user)
                if user_id:
                    rima_api_id = user_api_id.get(user_id)
            else:
                header = setup.user_alias.get(user)
                if not header:
                    header = setup.user_display[user]
            user_headers.append(header)

        api_ids = list(user_api_id.values())
        popularity_api = sorted(
            set(api_ids),
            key=lambda id_: api_ids.count(id_),
            reverse=True
            )
        api_num_list = [0]
        for user_i, user in enumerate(setup.users):
            user_id = user_id_dict.get(user)
            num = -1 * (user_i + 2)
            if user_id:
                num = popularity_api.index(user_api_id[user_id])
            api_num_list.append(num)

        headers = [cat.header, *user_headers]

        header_row = [TableCell(t) for t in headers]
        table = Table(
            table_orig_name, 'data-table', header_row, has_row_headers=True)
        table.styled_column[rima_col_i] = 'rima'

        for row_num, label in enumerate(label_names):
            # Add combat row
            if table_name == 'skill' and row_num == 1:
                users_ids = [(u, user_id_dict.get(u)) for u in setup.users]
                combat_row = self._get_combat_row(
                    user_data, label_display, users_ids)
                self._diff_format_row(
                    combat_row, rima_col_i, api_num_list, is_rank, is_diff)
                table.add_row(combat_row)
                table.styled_row[2] = 'combat'

            row_header = label_display[label]
            row = [TableCell(row_header)]
            all_zeroes = True
            for user in setup.users:
                value = '<err>'
                user_id = user_id_dict.get(user)
                try:
                    data = user_data[user_id]
                except KeyError:
                    pass
                else:
                    try:
                        value = data[label]
                    except KeyError:
                        value = 'n/a'
                    else:
                        if value not in (0, -1):
                            all_zeroes = False

                if is_rank and value == -1:
                    value = text = '-'
                elif isinstance(value, Number):
                    text = self.format_number(value)
                else:
                    text = str(value)
                row.append(TableCell(text, value))

            if 'activity' in table_name and all_zeroes:
                continue

            self._diff_format_row(
                row, rima_col_i, api_num_list, is_rank, is_diff)
            table.add_row(row)

        return table

    def _get_combat_row(self, user_data, label_display, users_ids):
        # user_data   [user_id] [label] = value
        # label_display         [label] = display

        skill_names = (
            'attack', 'strength', 'defence', 'prayer', 'magic', 'ranged',
            'hitpoints'
            )
        SkillTuple = namedtuple('SkillTuple', skill_names)

        cell_values = ['Combat']
        for user, user_id in users_ids:
            skill_values = user_data.get(user_id)
            if not skill_values:
                cell_values.append('<err>')
                continue
            levels = SkillTuple(
                *(skill_values.get(name) for name in skill_names))
            combat_level = self._get_combat_level(levels)
            cell_values.append(combat_level)
        combat_row = [TableCell(v) for v in cell_values]
        return combat_row

    def _get_combat_level(self, lvl):
        if any(not isinstance(s, Number) for s in lvl):
            return 'n/a'
        base = 0.25 * (lvl.defence + lvl.hitpoints + lvl.prayer//2)
        melee = lvl.attack + lvl.strength
        ranged = lvl.ranged * 3 // 2
        mage = lvl.magic * 3 // 2
        combat_level = math.floor(base + 0.325 * max(melee, ranged, mage))
        return combat_level

    def _diff_format_row(
        self, row, rima_col_i, api_num_list, is_rank, is_diff
    ):
        if rima_col_i == -1:
            return

        rima_val = row[rima_col_i].value
        rima_api_num = api_num_list[rima_col_i]
        for col_i in range(1, len(row)):
            if col_i == rima_col_i:
                continue

            cell = row[col_i]
            api_num = api_num_list[col_i]
            is_same_api = (api_num == rima_api_num)
            can_compare = not (not is_same_api and is_rank)

            if can_compare:
                self._judge_colour(cell, rima_val, is_rank)

            if is_diff:
                self._apply_diff_to_cell(cell, rima_val, can_compare)

    def _judge_colour(self, cell, rima_val, is_rank):
        is_available = isinstance(cell.value, Number)
        rima_available = isinstance(rima_val, Number)

        # Classify colours
        judgement = None
        if is_rank and is_available and not rima_available:
            judgement = 'good'
        elif is_rank and not is_available and rima_available:
            judgement = 'bad'
        elif is_available and rima_available:
            val_a = cell.value
            val_b = rima_val
            if is_rank:
                val_a, val_b = val_b, val_a
            if val_a > val_b:
                judgement = 'good'
            elif val_a < val_b:
                judgement = 'bad'
        if judgement:
            # JUDGE !
            cell.style_classes.append(judgement)

    def _apply_diff_to_cell(self, cell, rima_val, can_compare):
        is_available = isinstance(cell.value, Number)
        rima_available = isinstance(rima_val, Number)

        if is_available and rima_available and can_compare:
            cell.value = cell.value - rima_val
            cell.text = self.format_number(cell.value, show_plus=True)
        elif is_available or not can_compare:
            cell.value = 0
            cell.text = 'n/a'

    def _echo_tables(self, tables, term_cols):
        last_i = len(tables) - 1
        for table_i, table in enumerate(tables):
            lines = table.render_lines()
            for line in lines:
                click.echo(line)
            if table_i != last_i:
                click.echo()
