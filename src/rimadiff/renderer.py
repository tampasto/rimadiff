import json
import math
import urllib.parse
from collections import Counter
from datetime import date, datetime
from numbers import Number

import requests

from rimadiff.rimadiff_common import RimadiffCommon
from rimadiff.table_cell import TableCell


class Renderer(RimadiffCommon):
    CATEGORY_HEADERS = [
        'Skill level', 'Skill xp', 'Skill rank',
        'Activity', 'Activity rank'
        ]

    def __init__(self, config, history_manager):
        self.config = config
        self.history_manager = history_manager

        self._users = None
        self._user_orig = None
        self._user_alias = None
        self._rima = None
        self._force_download = False
        self._show_difference = False

        self._download_success_users = []
        self._download_fail_users = []
        self._download_fail_errors = Counter()
        self._bad_json_users = []
        self._wrong_user_data = []

    def print_tables(
        self, setup_name, force_download, show_difference, show_table
    ):
        setup = self.config.get_user_setup(setup_name)
        self._users = setup.users
        self._user_orig = setup.user_orig
        self._user_alias = setup.user_alias
        self._rima = setup.rima
        self._rima_orig = setup.rima_orig

        self._force_download = force_download
        self._show_difference = show_difference

        no_rima = not self._rima
        invalid_rima = self._rima not in self._users
        if no_rima or invalid_rima:
            # Complain about RIMA
            prolog = ''
            if show_difference:
                prolog = 'Cannot calculate differences, '
            epilog = ('set' if no_rima else f'a user ({self._rima_orig})')
            if show_difference or (invalid_rima and not no_rima):
                self.warning(f'{prolog}RIMA is not {epilog}.')
                self._show_difference = False

        self.history_manager.open_connection()

        err = None
        user_data = na_users = None
        now = datetime.now().astimezone()
        try:
            user_data, na_users, user_history_time = (
                self._source_user_data(now))
            category_tables, rima_cols = self._build_tables(
                user_data, na_users, now)
        except Exception as error:
            err = error
        finally:
            self.history_manager.close_connection()
        if err:
            raise err

        print()

        dl_success = self._download_success_users
        user_map = self._user_orig.get
        if len(dl_success):
            print(
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
                print(f'{count_text}{text}')
            print()
        json_fail = self._bad_json_users
        if len(json_fail):
            self.error('Bad API JSON: ' + ', '.join(map(user_map, json_fail)))
        if len(self._wrong_user_data):
            self.error(
                'API returned data for wrong users, snapshots not saved in '
                'history:'
                )
            for user, user_response in self._wrong_user_data:
                print(f'  Requested {user_map(user)}, got {user_response}')
            print()

        if len(user_history_time):
            print('Fetched at', end='')
            if len(set(user_history_time.values())) == 1:
                time, timezone = next(iter(user_history_time.values()))
                print(f' {time} {timezone}\n')
            else:
                is_variable_tz = len(
                    set(t[1] for t in user_history_time.values())
                    ) > 1
                _, timezone = next(iter(user_history_time.values()))
                print(('' if is_variable_tz else f' ({timezone})'))
                sorted_items = sorted(
                    user_history_time.items(), key=lambda item: item[1][0])
                for user, (time, timezone) in sorted_items:
                    print(
                        time + (f' ({timezone})' if is_variable_tz else '')
                        + f' {user_map(user)}'
                        )
                print()

        self._add_combat_level(category_tables[0])
        print_tables = []
        if show_table['skill']:
            print_tables.append((
                category_tables[0], rima_cols[0], False, False))
        if show_table['xp']:
            print_tables.append((
                category_tables[1], rima_cols[1], False, False))
        if show_table['skill-rank']:
            print_tables.append((
                category_tables[2], rima_cols[2], False, True))
        if show_table['activity']:
            print_tables.append((
                category_tables[3], rima_cols[3], True, False))
        if show_table['activity-rank']:
            print_tables.append((
                category_tables[4], rima_cols[4], True, True))
        for table, rima_col_i, hide_if_zero, comp_rank in print_tables:
            self._print_user_compare_table(
                table, hide_if_zero, comp_rank, rima_col_i)


    def _source_user_data(self, now):
        # user_data[user_id][category][label_id] = value
        user_data = {}
        na_users = set() # Data not available

        today_ordinal = now.toordinal()
        now_time = now.strftime('%H:%M')
        now_timezone = now.strftime('%z')
        db_users, new_users = self.history_manager.sort_users(
            set(self._users))

        def push_to_dict(data, user, user_id):
            if data is None:
                na_users.add(user)
            else:
                user_data[user_id] = data

        user_history_time = {}
        with requests.Session() as session:
            for user_id, user in db_users:
                data = None
                if not self._force_download:
                    data, time, timezone = self.history_manager.read_data(
                        today_ordinal, user_id)
                    if time is not None:
                        user_history_time[user] = time, timezone
                if data is None:
                    r = self._download_data(user, session)
                    data, category_labels, url, skip_write = r

                    if data is not None and not skip_write:
                        self.history_manager.write_data(
                            today_ordinal, user_id, data, category_labels,
                            now_time, now_timezone, url
                            )
                        user_original = self._user_orig[user]
                        self.history_manager.update_user_original(
                            user_id, user_original)
                push_to_dict(data, user, user_id)

            for user in new_users:
                r = self._download_data(user, session)
                data, category_labels, url, skip_write = r

                user_id = None
                if data is not None and not skip_write:
                    user_original = self._user_orig[user]
                    user_id = self.history_manager.add_user(
                        user, user_original)
                    self.history_manager.write_data(
                        today_ordinal, user_id, data, category_labels,
                        now_time, now_timezone, url
                        )
                push_to_dict(data, user, user_id)
        return user_data, na_users, user_history_time

    def _build_tables(self, user_data, na_users, now):
        # label_id_rows[category] = [label_id, label_id, ...]
        category_stop = len(Renderer.CATEGORY_HEADERS)
        label_id_row_sets = [set() for _ in range(category_stop)]
        for data in user_data.values():
            for category, label_values in enumerate(data):
                label_id_row_sets[category].update(range(len(label_values)))
        label_id_rows = [sorted(label_ids) for label_ids in label_id_row_sets]

        user_column_headers = []
        rima_cols = []
        rima_col_i = -1
        for user_i, user in enumerate(self._users):
            col_header = self._user_orig[user]

            # Nayta dorkalle RIMA
            if user == self._rima:
                col_header = 'RIMA'
                rima_col_i = user_i + 1

            elif user in self._user_alias:
                col_header = self._user_alias[user]

            user_column_headers.append(col_header)
        rima_cols = [rima_col_i] * category_stop

        category_tables = []
        user_id_dict = self.history_manager.get_user_id_dict()
        today_ordinal = now.toordinal()
        for category in range(category_stop):
            header_row = [
                Renderer.CATEGORY_HEADERS[category], *user_column_headers]
            table = [header_row]
            for label_id in label_id_rows[category]:
                for user in self._users:
                    user_id = user_id_dict[user]
                    label = self.history_manager.get_label(
                        category, label_id, today_ordinal, user_id)
                    if label is not None:
                        break
                row = [label]
                for user in self._users:
                    value = '-'
                    if user in na_users:
                        value = 'n/a'
                    else:
                        user_id = user_id_dict[user]
                        try:
                            value = user_data[user_id][category][label_id]
                        except (IndexError, KeyError):
                            pass
                    if value == -1:
                        value = '-'
                    row.append(value)
                table.append(row)
            category_tables.append(table)

        return category_tables, rima_cols

    def _download_data(self, user, session):
        data = None
        category_labels = None
        user_original = self._user_orig[user]
        quoted_user = urllib.parse.quote(user_original, safe='')
        url = self.config.api_url.format(quoted_user)
        resp = None
        try:
            resp = session.get(url)
            resp.raise_for_status()
        except requests.RequestException as err:
            self._download_fail_users.append(user)
            err_str = f'{type(err).__name__}: {err}'
            self._download_fail_errors[err_str] += 1
            resp = None

        skip_write = False
        if resp:
            self._download_success_users.append(user)
            obj = resp.json()
            data, category_labels, user_response = (
                self._response_json_to_data(obj))
            if data is None:
                self._bad_json_users.append(user)
            elif user != user_response.lower():
                self._wrong_user_data.append((user, user_response))
                skip_write = True
        return data, category_labels, url, skip_write

    def _response_json_to_data(self, obj):
        user_response = obj['name']

        # data[category][label_id] = value
        # category_labels[category][label_id] = label
        if (not isinstance(obj.get('skills'), list)
            or not isinstance(obj.get('activities'), list)):
            return None, None
        skills_fields = ['level', 'xp', 'rank']
        skills_max_id = max(entry['id'] for entry in obj['skills'])
        skills_empty = [None] * (skills_max_id + 1)
        skills_categories = [skills_empty.copy() for _ in skills_fields]
        skills_category_labels = [skills_empty.copy() for _ in skills_fields]
        for entry in obj['skills']:
            for field_i, field in enumerate(skills_fields):
                id_ = entry['id']
                skills_categories[field_i][id_] = entry[field]
                skills_category_labels[field_i][id_] = entry['name']

        activity_fields = ['score', 'rank']
        activity_max_id = max(entry['id'] for entry in obj['activities'])
        activity_empty = [None] * (activity_max_id + 1)
        activity_categories = [activity_empty.copy() for _ in activity_fields]
        activity_category_labels = [
            activity_empty.copy() for _ in activity_fields]
        for entry in obj['activities']:
            for field_i, field in enumerate(activity_fields):
                id_ = entry['id']
                activity_categories[field_i][id_] = entry[field]
                activity_category_labels[field_i][id_] = entry['name']

        data = [*skills_categories, *activity_categories]
        category_labels = [*skills_category_labels, *activity_category_labels]
        return data, category_labels, user_response

    def _add_combat_level(self, table_skill_level):
        combat_row = ['Combat']
        for col_i in range(1, len(table_skill_level[0])):
            levels = {
                row[0]: row[col_i]
                for row in table_skill_level[1:]
                }
            combat_level = self._get_combat_level(levels)
            combat_row.append(combat_level)
        table_skill_level.insert(2, combat_row)

    def _get_combat_level(self, levels):
        base = (
            0.25
            * (levels['Defence'] + levels['Hitpoints'] + levels['Prayer']//2)
            )
        melee = levels['Attack'] + levels['Strength']
        ranged = levels['Ranged'] * 3 // 2
        mage = levels['Magic'] * 3 // 2
        combat_level = math.floor(base + 0.325 * max(melee, ranged, mage))
        return combat_level

    def _print_user_compare_table(
        self, raw_table, hide_if_zero, comp_rank, rima_col_i
    ):
        table = []
        for row_i, raw_row in enumerate(raw_table):
            if hide_if_zero and all(v == 0 or v == '-' for v in raw_row[1:]):
                continue

            rima_val = None
            if rima_col_i != -1:
                rima_val = raw_row[rima_col_i]
            row = []
            for col_i, value in enumerate(raw_row):
                text = str(value)
                if isinstance(value, Number):
                    if (rima_col_i != -1 and self._show_difference
                        and col_i != rima_col_i):
                        # Calculate diff column
                        text, value = self._get_diff_text(value, rima_val)
                    else:
                        text = self._format_numeric(value)

                cell = TableCell(text, value, row_i, col_i)
                row.append(cell)
            table.append(row)

        for row_i, row in enumerate(table):
            row_bg = ('black' if row_i % 2 == 0 else 'darkgray')
            for cell in row:
                cell.bg = row_bg
                if rima_col_i != -1:
                    rima_val = row[rima_col_i].value
                    self._color_user_compare_cell(
                        cell, rima_val, rima_col_i, comp_rank)

        self._print_table(table)

    def _get_diff_text(self, value, rima_val):
        if isinstance(rima_val, Number):
            value = value - rima_val
            text = self._format_numeric(value, show_plus=True)
        else:
            value = 0
            text = 'n/a'
        return text, value

    def _format_numeric(self, value, show_plus=False):
        sign = ('+' if show_plus and value > 0 else '')
        text = f'{value:{sign},}'.replace(',', ' ')
        return text

    def _color_user_compare_cell(self, cell, rima_val, rima_col_i, comp_rank):
        # Highlight RIMA
        if cell.col_i == rima_col_i:
            cell.bold = True
            if cell.is_column_header:
                cell.bg = 'orange'
            else:
                cell.fg = 'orange'
            return

        if cell.is_column_header or cell.is_row_header:
            cell.bold = True
            return

        is_available = isinstance(cell.value, Number)
        rima_available = isinstance(rima_val, Number)
        show_diff = self._show_difference

        if comp_rank and is_available and not rima_available:
            cell.fg = 'green'
        elif comp_rank and not is_available and rima_available:
            cell.fg = 'red'
        elif is_available and rima_available:
            val_a = cell.value
            val_b = (0 if show_diff else rima_val)
            if comp_rank:
                val_a, val_b = val_b, val_a
            if val_a > val_b:
                cell.fg = 'green'
            elif val_a < val_b:
                cell.fg = 'red'

    def _print_table(self, table):
        lens = [max(map(len, column)) for column in zip(*table)]
        for row in table:
            for cell in row:
                cell.width = lens[cell.col_i]
                cell.print()
            # Reset colors at the end of row
            print(self.term_color())
        print()

    def list_history(self):
        snapshots = None
        if self.history_manager.history_exists():
            self.history_manager.open_connection()
            snapshots = self.history_manager.get_history_snapshots()
            self.history_manager.close_connection()
        else:
            print(
                '\nHistory database does not exist.\n\n'
                f'Path: {self.history_manager.db_path}\n'
                )
            return

        headers = ['Num', 'Time']
        align = ['right', 'center']
        table = [[TableCell(h, h, 0, i, align[i], bold=True) for i, h in enumerate(headers)]]
        for snapshot_i, (date_ordinal, time, timezone) in enumerate(snapshots):
            date_obj = date.fromordinal(date_ordinal)
            num = len(snapshots) - snapshot_i
            time = f'{date_obj} {time} {timezone}'
            text_values = [(f'{num}', num), (time, date_ordinal)]
            row_fg = ('white' if snapshot_i % 2 == 1 else 'blue')
            table.append([
                TableCell(text, value, snapshot_i, i, align[i], fg=row_fg)
                for i, (text, value) in enumerate(text_values)
                ])
        print()
        self._print_table(table)

    def list_users(self, setup_name):
        counts = latest_snapshot = None
        if self.history_manager.history_exists():
            self.history_manager.open_connection()
            counts, latest_snapshot = self.history_manager.get_info_users()
            self.history_manager.close_connection()
        # counts: U.name_original, U.name, Count(R.date_ordinal)
        # latest_snapshot: U.name, R2.date_ordinal, R2.time, R2.timezone

        setup = self.config.get_user_setup(setup_name)
        users = setup.users
        user_orig = setup.user_orig.copy()
        user_alias = setup.user_alias
        user_alias_lc = {n.lower(): a for n, a in user_alias.items()}
        rima_lc = setup.rima

        user_set = set(users) # Config
        if counts is not None: # History database
            user_set |= (
                {r[1] for r in counts} | {r[0] for r in latest_snapshot})

        # If both database and config aliases, show config aliases
        if counts is not None:
            user_orig |= {r[1]: r[0] for r in counts if r[1] not in user_orig}

        header = ['Name', 'Alias', 'RIMA', 'Snapshots', 'Latest snapshot']
        align = ['left', 'left', 'center', 'right', 'center']
        table = [[
            TableCell(h, h, 0, i, align[i], bold=True)
            for i, h in enumerate(header)
            ]]

        tz_set = set()
        if latest_snapshot is not None:
            tz_set = {t[3] for t in latest_snapshot}
        same_tz = (len(tz_set) == 1)
        for row_i, user_lc in enumerate(sorted(user_set)):
            snapshots = latest_date = '-'
            date_ordinal = -1
            if counts is not None:
                count_row = next(r for r in counts if r[1] == user_lc)
                snapshot_row = next(
                    r for r in latest_snapshot if r[0] == user_lc)

                snapshots = count_row[2]
                _, date_ordinal, time, timezone = snapshot_row

                tz_part = ('' if same_tz else f' {timezone}')
                if date_ordinal is not None:
                    latest_date = (
                        f'{date.fromordinal(date_ordinal)} {time}{tz_part}')

            user = user_orig[user_lc]
            alias = user_alias.get(user_lc, '-')
            is_rima = ('X' if user_lc == rima_lc else '')
            text_values = [
                (user, user),
                (alias, alias),
                (is_rima, is_rima),
                (str(snapshots), snapshots),
                (latest_date, date_ordinal),
                ]
            row_fg = ('white' if row_i % 2 == 1 else 'blue')
            row = [
                TableCell(text, value, row_i, i, align[i], fg=row_fg)
                for i, (text, value) in enumerate(text_values)
                ]
            table.append(row)
        print()
        self._print_table(table)
        tz_info = ''
        if same_tz:
            tz_info = f' Timezone {next(iter(tz_set))}.'
        print(f'Aliases and RIMA from user setup "{setup_name}".{tz_info}\n')

    def list_paths(self):
        align = ['left', 'left', 'left', 'right', 'center']
        header = ['Name', 'Path', 'Source', 'Size', 'Modified']
        time_fmt = '%Y-%m-%d %H:%M'

        table = [[
            TableCell(h, h, 0, i, align[i], bold=True)
            for i, h in enumerate(header)
            ]]
        paths = [
            ('Configuration', self.config.path, False),
            ('History database', self.config.history_path,
                self.config.history_path_from_config)
            ]
        hyphen_desc = False
        errs = []
        for row_i, (name, path, from_config) in enumerate(paths):
            row_fg = ('white' if row_i % 2 == 1 else 'blue')

            source = ('Config' if from_config else '-')
            size = '<err>'
            modified = '<err>'
            try:
                st = path.stat()
            except FileNotFoundError:
                size = modified = '-'
                hyphen_desc = True
            except OSError as err:
                errs.append(str(err))
            else:
                size = self._size_format(st.st_size)
                mod_dt = datetime.fromtimestamp(st.st_mtime)
                modified = mod_dt.strftime(time_fmt)

            row = (name, str(path), source, size, modified)
            table.append([
                TableCell(t, t, row_i, i, align[i], fg=row_fg)
                for i, t in enumerate(row)
                ])

        print()
        if errs:
            self.error('\n'.join(errs))

        self._print_table(table)

        tz = datetime.now().astimezone().strftime('%z')
        hyphen_info = ''
        if hyphen_desc:
            hyphen_info = 'Hyphen in Size means the file does not exist. '
        print(f'{hyphen_info}Timezone {tz}.\n')

    def _size_format(self, size):
        if size/10 > 1024**3:
            return f'{size//1024**3}G'
        elif size/10 > 1024**2:
            return f'{size//1024**2}M'
        elif size/10 > 1024:
            return f'{size//1024}k'
        return f'{size}'



