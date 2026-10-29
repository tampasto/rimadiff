import copy
import json
import math
import urllib.parse
from collections import Counter, namedtuple
from datetime import date, datetime
from numbers import Number

import click
import requests

from rimadiff.api_response import APIResponse
from rimadiff.history_manager import HistoryManager
from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.table import Table
from rimadiff.table_cell import TableCell


class Renderer(RimadiffCommon):
    def __init__(self, config):
        self.config = config

        self._force_download = False

        self._download_success_users = []
        self._download_fail_users = []
        self._download_fail_errors = Counter()
        self._bad_json_users = []
        self._wrong_user_data = []
        self._non_numeric_categories = {}
        self._non_int_categories = {}

    def print_tables(self, setup_name, force_download, table_names):
        setup = self.config.get_user_setup(setup_name)

        self._force_download = force_download

        self._validate_rima(setup, table_names)

        err = None
        now = datetime.now().astimezone()
        today_ordinal = now.toordinal()

        history_path = self.config.history_path
        users_rima_first = sorted(setup.users, key=lambda u: (u != setup.rima, u))

        clean_table_names = [n.removesuffix('-diff') for n in table_names]
        categories = [
            c.category for c in HistoryManager.CATEGORIES
            if c.table_name in clean_table_names
            ]

        with HistoryManager(history_path) as history:
            cat_data, user_history_time = (
                self._source_user_data(history, now, setup, categories))

            user_id_dict = history.get_user_id_dict()

            label_dict = history.get_label_dict(
                users_rima_first, today_ordinal, categories)

        tables = []
        for name in table_names:
            table_name = name
            is_diff = False
            if name.endswith('-diff'):
                table_name = name.removesuffix('-diff')
                is_diff = True
            table = self._generate_table(
                table_name, is_diff, setup, cat_data, label_dict, user_id_dict,
                today_ordinal
                )
            tables.append(table)

        click.echo()
        dl_success = self._download_success_users
        user_map = setup.user_orig.get
        if len(dl_success):
            click.echo(
                'Downloaded: '
                + ', '.join(map(user_map, dl_success)) + '\n'
                )

        dl_fail = self._download_fail_users
        if len(dl_fail):
            self.error(
                'Could not download: ' + ', '.join(map(user_map, dl_fail)))

        dl_errors = self._download_fail_errors
        if dl_errors.total():
            for text, count in dl_errors.items():
                count_text = f'[{count}x] ' if count > 1 else ''
                self.error(f'{count_text}{text}')
            click.echo()

        json_fail = self._bad_json_users
        if len(json_fail):
            self.error('Bad API JSON: ' + ', '.join(map(user_map, json_fail)))

        if len(self._wrong_user_data):
            self.error(
                'API returned data for wrong users, snapshots not saved in '
                'history:'
                )
            for user, user_response in self._wrong_user_data:
                click.echo(f'  Requested {user_map(user)}, got {user_response}')
            click.echo()

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
                        + ', '.join(setup.user_orig[u] for u in users)
                        )
            click.echo(fetch_text + '\n')

        numeric_errs = (
            (self._non_numeric_categories, 'numeric'),
            (self._non_int_categories, 'integer')
            )
        for num_dict, label in numeric_errs:
            if len(num_dict) == 0:
                continue
            self.warning(f'The API returned non-{label} datapoints for:')
            cat_header = {c.category: c.header for c in HistoryManager.CATEGORIES}
            for category, value_counter in num_dict.items():
                vals = ', '.join(
                    repr(val) + ('' if count == 1 else f' (x{count})')
                    for val, count in value_counter.items()
                    )
                click.echo(f'  {cat_header[category]}: {vals}')

        for table in tables:
            lines = table.render_lines()
            for line in lines:
                click.echo(line)
            click.echo()

        RimadiffCommon.print_colour_warnings()

    def _validate_rima(self, setup, table_names):
        no_rima = not setup.rima
        invalid_rima = setup.rima not in setup.users
        if no_rima or invalid_rima:
            # Complain about RIMA
            prolog = ''
            has_diff_tables = any(n.endswith('-diff') for n in table_names)
            if has_diff_tables:
                prolog = 'Cannot calculate differences, '
            epilog = ('set' if no_rima else f'a user ({setup.rima_orig})')
            if has_diff_tables or (invalid_rima and not no_rima):
                self.warning(f'{prolog}RIMA is not {epilog}.')
                for i in range(len(table_names)):
                    table_names[i] = table_names[i].removesuffix('-diff')

    def _source_user_data(self, history, now, setup, categories):
        # cat_data[category][user_id][label_id] = value
        cat_data = {n: {} for n in categories}

        today_ordinal = now.toordinal()
        now_time = now.strftime('%H:%M')
        now_timezone = now.strftime('%z')
        time_tuple = today_ordinal, now_time, now_timezone

        db_users, new_users = history.sort_users(set(setup.users))

        # Read data for today from history database
        user_db_data = {}
        user_history_time = {}
        # user_db_data[user_id][category][label_id] = value
        # user_history_time[user_id] = (time, timezone)
        if not self._force_download:
            user_ids = [t[0] for t in db_users]
            user_db_data, user_history_time = history.read_data(
                today_ordinal, user_ids, categories)

        sourced: list[APIResponse] = []
        with requests.Session() as session:
            ctx = session, history # Context managers

            for user_id, user in db_users:
                user_tuple = user, user_id, setup
                db_data = user_db_data.get(user_id)

                self._source_existing_user(db_data, user_tuple, ctx, sourced)

            for user in new_users:
                self._source_new_user(user, setup, today_ordinal, ctx, sourced)

        # Add only requested table categories to cat_data, including db
        # pseudo-responses
        for resp in sourced:
            for category in categories:
                cat_data[category][resp.user_id] = resp.data[category]

        # Write new data to database
        downloaded = [r for r in sourced if r.url]
        if downloaded:
            history.write_data(time_tuple, downloaded)

        return cat_data, user_history_time

    def _source_existing_user(self, db_data, user_tuple, ctx, sourced):
        user, user_id, setup  = user_tuple
        session, history = ctx

        user_original = setup.user_orig[user]
        history.update_user_original(user_id, user_original)

        labels = None
        if db_data:
            # Package in pseudo-response
            resp = APIResponse(db_data, labels={}, url=None, user_id=user_id)
        else:
            resp = self._download_data(user, setup, session)
            if not resp:
                return

        resp.user_id = user_id
        sourced.append(resp)

    def _source_new_user(self, user, setup, today_ordinal, ctx, sourced):
        session, history = ctx

        resp = self._download_data(user, setup, session)
        if not resp:
            return

        user_original = setup.user_orig[user]
        resp.user_id = history.add_user(user, user_original, today_ordinal)

        sourced.append(resp)

    def _download_data(self, user, setup, session):
        # data   [category] [label_id] = value
        # labels [category] [label_id] = label

        user_original = setup.user_orig[user]
        quoted_user = urllib.parse.quote(user_original, safe='')
        url = self.config.api_url.format(quoted_user)

        resp = None
        try:
            r = session.get(url)
            r.raise_for_status()
        except requests.RequestException as err:
            self._download_fail_users.append(user)
            err_str = f'{type(err).__name__}: {err}'
            self._download_fail_errors[err_str] += 1
        else:
            self._download_success_users.append(user)
            obj = r.json()
            data, labels, user_response = self._response_json_to_data(obj)
            if data is None:
                self._bad_json_users.append(user)
            elif user != user_response.lower():
                self._wrong_user_data.append((user_original, user_response))
            else:
                resp = APIResponse(data, labels, url)

        return resp

    def _response_json_to_data(self, obj):
        # data   [category] [label_id] = value
        # labels [category] [label_id] = label

        user_response = str(obj.get('name')).strip()
        skills = obj.get('skills')
        activities = obj.get('activities')

        not_list = lambda v: not isinstance(v, list)

        if not_list(skills) or not_list(activities):
            return None, None, None

        data = {c.category: {} for c in HistoryManager.CATEGORIES}
        labels = copy.deepcopy(data)

        sk_field_table = {
            'level': 'skill',
            'xp':    'xp',
            'rank':  'skill-rank'
            }
        self._add_json_portion(skills, sk_field_table, data, labels)

        act_field_table = {
            'score': 'activity',
            'rank':  'activity-rank'
            }
        self._add_json_portion(activities, act_field_table, data, labels)

        return data, labels, user_response

    def _add_json_portion(self, obj, field_table, data, labels):
        field_category = {}
        db_cat = HistoryManager.CATEGORIES
        for field, table_name in field_table.items():
            field_category[field] = next(
                c.category for c in db_cat if c.table_name == table_name)

        for entry in obj:
            id_ = entry['id']
            for field in field_table:
                category = field_category[field]

                val = entry[field]
                if not isinstance(val, Number):
                    self._record_numeric_data_type_error(category, field, val)
                elif not isinstance(val, int):
                    self._record_numeric_data_type_error(
                        category, field, val, True)
                data[category][id_] = val

                labels[category][id_] = str(entry['name']).strip()

    def _record_numeric_data_type_error(self, category, field, val, for_int=False):
        err_dict = self._non_numeric_categories
        if for_int:
            err_dict = self._non_int_categories
        err_dict.setdefault(category, Counter())
        err_dict[category][val] += 1

    def _generate_table(
        self, table_name, is_diff, setup, cat_data, label_dict, user_id_dict,
        today_ordinal
    ):
        # cat_data   [category] [user_id] [label_id] = value
        # label_dict [category]           [label_id] = label

        cat = next(c for c in HistoryManager.CATEGORIES if c.table_name == table_name)
        user_data = cat_data[cat.category]
        label_value = label_dict[cat.category]
        # user_data   [user_id] [label_id] = value
        # label_value           [label_id] = label
        is_rank = ('-rank' in table_name)

        label_id_set = set()
        for lab_dict in user_data.values():
            label_id_set |= set(lab_dict.keys())
        label_ids = sorted(label_id_set)

        rima_col_i = -1
        user_headers = []
        for user_i, user in enumerate(setup.users):
            if user == setup.rima:
                # Nayta dorkalle RIMA
                header = 'RIMA'
                rima_col_i = user_i + 1
            else:
                header = setup.user_alias.get(user)
                if not header:
                    header = setup.user_orig[user]
            user_headers.append(header)
        headers = [cat.header, *user_headers]

        header_row = [TableCell(t) for t in headers]
        table = Table(
            table_name, 'data-table', header_row, has_row_headers=True)
        table.styled_column[rima_col_i] = 'rima'

        for row_num, label_id in enumerate(label_ids):
            # Add combat row
            if table_name == 'skill' and row_num == 1:
                combat_row = self._get_combat_row(
                    user_data, label_value, setup.users)
                self._diff_format_row(combat_row, rima_col_i, is_rank, is_diff)
                table.add_row(combat_row)
                table.styled_row[2] = 'combat'

            label = label_value[label_id]
            row = [TableCell(label)]
            all_zeroes = True
            for user in setup.users:
                value = 'n/a'
                user_id = user_id_dict[user]
                try:
                    value = user_data[user_id][label_id]
                except KeyError:
                    pass
                else:
                    if value not in (0, -1):
                        all_zeroes = False

                if is_rank and value == -1:
                    value = text = '-'
                elif isinstance(value, Number):
                    text = self._format_numeric(value)
                else:
                    text = str(value)
                row.append(TableCell(text, value))

            if 'activity' in table_name and all_zeroes:
                continue

            self._diff_format_row(row, rima_col_i, is_rank, is_diff)
            table.add_row(row)

        return table

    def _get_combat_row(self, user_data, label_value, users):
        # user_data   [user_id] [label_id] = value
        # label_value           [label_id] = label

        skill_names = (
            'attack', 'strength', 'defence', 'prayer', 'magic', 'ranged',
            'hitpoints'
            )
        SkillTuple = namedtuple('SkillTuple', skill_names)

        skill_ids = tuple(
            next(
                (i for i, v in label_value.items() if str(v).strip().lower() == s),
                None)
            for s in skill_names
            )

        cell_values = ['Combat']
        for user_i, user in enumerate(users):
            skill_values = user_data[user_i]
            levels = SkillTuple(*(skill_values.get(id_) for id_ in skill_ids))
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

    def _diff_format_row(self, row, rima_col_i, is_rank, is_diff):
        if rima_col_i == -1:
            return

        rima_val = row[rima_col_i].value
        for col_i in range(1, len(row)):
            if col_i == rima_col_i:
                continue
            cell = row[col_i]

            self._judge_colour(cell, rima_val, is_rank)

            if is_diff:
                self._apply_diff_to_cell(cell, rima_val)

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

    def _apply_diff_to_cell(self, cell, rima_val):
        is_available = isinstance(cell.value, Number)
        rima_available = isinstance(rima_val, Number)

        if is_available and rima_available:
            cell.value = cell.value - rima_val
            cell.text = self._format_numeric(cell.value, show_plus=True)
        elif is_available:
            cell.value = 0
            cell.text = 'n/a'

    def _format_numeric(self, value, show_plus=False):
        sign = ('+' if show_plus and value > 0 else '')
        text = f'{value:{sign},}'.replace(',', ' ')
        return text

    def list_history(self):
        snapshots = None
        history_path = self.config.history_path
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

    def list_users(self, setup_name):
        counts = latest_snapshot = None

        history_path = self.config.history_path
        setup = self.config.get_user_setup(setup_name)
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

    def list_paths(self):
        paths = [
            ['General config', self.config.path, '', False],
            ['Colour config', self.config.colour_path, '', False],
            ['History database', self.config.history_path, '',
                self.config.history_path_from_config]
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



