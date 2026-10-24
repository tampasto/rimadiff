import argparse
import json
import math
import tomllib
import urllib.parse
from collections import Counter
from datetime import date, datetime, UTC
from numbers import Number
from pathlib import PurePath, Path

import requests
from platformdirs import PlatformDirs

from rimadiff.history_manager import HistoryManager


CONFIG_PATH = '~/.config/rimadiff.toml'


class UserSetup:
    def __init__(self, setup):
        self.users = [u.lower() for u in setup['users']]
        self.user_orig = {u.lower(): u for u in setup['users']}
        self.user_alias = {
            u.lower(): a for u, a in setup['user_alias'].items()}
        self.rima = setup['rima'].lower()


class TableCell:
    ALIGN = {'right': '>', 'left': '<', 'center': '^'}

    def __init__(
        self, text, value, row_i, col_i, align='right', bg='black', fg='white',
        bold=False
    ):
        self.text = text
        self.value = value
        self.row_i = row_i
        self.col_i = col_i
        self.align = align
        self.bg = bg
        self.fg = fg
        self.bold = bold

        self.width = -1

    def __str__(self):
        return self.text

    def __len__(self):
        return len(self.text)

    @property
    def is_column_header(self):
        return self.row_i == 0

    @property
    def is_row_header(self):
        return self.col_i == 0

    def print(self):
        term_color = RimaDiffCli.terminal_color
        color_def = term_color(self.bg, self.bold, self.fg)
        align = TableCell.ALIGN[self.align]
        print(f'{color_def} {self.text:{align}{self.width}} ', end='')


class RimaDiffCli:
    CATEGORY_HEADERS = [
        'Skill level', 'Skill xp', 'Skill rank',
        'Activity', 'Activity rank'
        ]
    TERMINAL_COLORS = {
        'white': 107,
        'black': 40,
        'darkgray': 100,
        'green': 42,
        'red': 41,
        'orange': 43,
        'blue': 104,
    }

    @classmethod
    def terminal_color(self, bg=None, bold=False, fg='white'):
        if bg is None:
            return '\033[m'
        bold_def = ('1;' if bold else '')
        bg_def = self.TERMINAL_COLORS[bg]
        fg_def = self.TERMINAL_COLORS[fg] - 10
        return f'\033[{bold_def}{bg_def};{fg_def}m'

    def __init__(self, api_url, user_setup, history_manager):
        self.api_url = api_url
        self.user_setup = user_setup
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
        self, setup_name, force_download, show_difference,
        print_skills, print_xp, print_skill_rank,
        print_activities, print_activity_rank
    ):
        self._users = self.user_setup[setup_name].users
        self._user_orig = self.user_setup[setup_name].user_orig
        self._user_alias = self.user_setup[setup_name].user_alias
        self._rima = self.user_setup[setup_name].rima

        self._force_download = force_download
        self._show_difference = show_difference
        self.history_manager.open_connection()

        err = None
        user_data = na_users = None
        now = datetime.now().astimezone()
        try:
            user_data, na_users, user_history_time = (
                self._source_user_data(now))
            category_tables = self._build_tables(user_data, na_users, now)
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
        term_color = RimaDiffCli.terminal_color
        if len(dl_fail):
            print(
                term_color('red')
                + 'Could not download: '
                + ', '.join(map(user_map, dl_fail))
                + term_color() + '\n'
                )
        dl_errors = self._download_fail_errors
        if dl_errors.total():
            for text, count in dl_errors.items():
                count_text = f'[{count}x] ' if count > 1 else ''
                print(f'{count_text}{text}')
            print()
        json_fail = self._bad_json_users
        if len(json_fail):
            print(
                term_color('red')
                + 'Bad API JSON: '
                + ', '.join(map(user_map, json_fail))
                + term_color() + '\n'
                )
        if len(self._wrong_user_data):
            print(
                term_color('red')
                + 'API returned data for wrong users, snapshots not saved in '
                  'history:'
                + term_color()
                )
            for user, user_response in self._wrong_user_data:
                print(
                    '  ' + term_color('red')
                    + f'Requested {user_map(user)}, '
                      f'got {user_response}'
                    + term_color()
                    )
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
        if print_skills:
            print_tables.append((category_tables[0], False, False))
        if print_xp:
            print_tables.append((category_tables[1], False, False))
        if print_skill_rank:
            print_tables.append((category_tables[2], False, True))
        if print_activities:
            print_tables.append((category_tables[3], True, False))
        if print_activity_rank:
            print_tables.append((category_tables[4], True, True))
        for table, hide_if_zero, comp_rank in print_tables:
            self._print_user_compare_table(table, hide_if_zero, comp_rank)


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
        category_stop = len(RimaDiffCli.CATEGORY_HEADERS)
        label_id_row_sets = [set() for _ in range(category_stop)]
        for data in user_data.values():
            for category, label_values in enumerate(data):
                label_id_row_sets[category].update(range(len(label_values)))
        label_id_rows = [sorted(label_ids) for label_ids in label_id_row_sets]

        user_column_headers = []
        for user in self._users:
            col_header = self._user_orig[user]

            # Nayta dorkalle RIMA
            if user == self._rima:
                col_header = 'RIMA'

            elif user in self._user_alias:
                col_header = self._user_alias[user]

            user_column_headers.append(col_header)

        category_tables = []
        user_id_dict = self.history_manager.get_user_id_dict()
        today_ordinal = now.toordinal()
        for category in range(category_stop):
            header_row = [
                RimaDiffCli.CATEGORY_HEADERS[category], *user_column_headers]
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

        return category_tables

    def _download_data(self, user, session):
        data = None
        category_labels = None
        user_original = self._user_orig[user]
        quoted_user = urllib.parse.quote(user_original, safe='')
        url = self.api_url.format(quoted_user)
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

    def _print_user_compare_table(self, raw_table, hide_if_zero, comp_rank):
        rima_col_i = -1
        try:
            rima_col_i = raw_table[0].index('RIMA', 1)
        except ValueError:
            pass

        table = []
        for row_i, raw_row in enumerate(raw_table):
            if hide_if_zero and all(v == 0 or v == '-' for v in raw_row[1:]):
                continue

            if rima_col_i != -1:
                rima_val = raw_row[rima_col_i]
            row = []
            for col_i, value in enumerate(raw_row):
                text = str(value)
                if isinstance(value, Number):
                    if self._show_difference and col_i != rima_col_i:
                        text, value = self._get_diff_text(value, rima_val)
                    else:
                        text = self._format_numeric(value)

                cell = TableCell(text, value, row_i, col_i)

                self._color_user_compare_cell(
                    cell, rima_val, rima_col_i, comp_rank)
                row.append(cell)
            table.append(row)

        for row_i, row in enumerate(table):
            row_bg = ('black' if row_i % 2 == 0 else 'darkgray')
            for cell in row:
                cell.bg = row_bg

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
        sign = ('+' if show_plus else '')
        text = f'{value:{sign},}'.replace(',', ' ')
        return text

    def _color_user_compare_cell(self, cell, rima_val, rima_col_i, comp_rank):
        if cell.is_column_header or cell.is_row_header:
            cell.bold = True

        # Highlight RIMA
        if cell.col_i == rima_col_i:
            if cell.is_column_header:
                cell.bg = 'orange'
            else:
                cell.fg = 'orange'

        elif not cell.is_row_header and isinstance(cell.value, Number):
            val_a = cell.value
            val_b = (0 if self._show_difference else rima_val)
            if isinstance(val_b, Number):
                if comp_rank:
                    val_a, val_b = val_b, val_a
                if val_a > val_b:
                    cell.fg = 'green'
                    cell.bold = True
                elif val_a < val_b:
                    cell.fg = 'red'

    def _print_table(self, table):
        lens = [max(map(len, column)) for column in zip(*table)]
        term_color = RimaDiffCli.terminal_color
        for row in table:
            for cell in row:
                cell.width = lens[cell.col_i]
                cell.print()
            # Reset colors at the end of row
            print(term_color())
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
        table = [[TableCell(h, h, 0, i, align=align[i], bold=True) for i, h in enumerate(headers)]]
        for snapshot_i, (date_ordinal, time, timezone) in enumerate(snapshots):
            date_obj = date.fromordinal(date_ordinal)
            num = len(snapshots) - snapshot_i
            time = f'{date_obj} {time} {timezone}'
            text_values = [(f'{num}', num), (time, date_ordinal)]
            row_fg = ('white' if snapshot_i % 2 == 1 else 'blue')
            table.append([
                TableCell(text, value, snapshot_i, i, fg=row_fg, align=align[i])
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

        users = self.user_setup[setup_name].users
        user_orig = self.user_setup[setup_name].user_orig.copy()
        user_alias = self.user_setup[setup_name].user_alias
        user_alias_lc = {n.lower(): a for n, a in user_alias.items()}
        rima_lc = self.user_setup[setup_name].rima.lower()

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

    def list_paths(self, config_path, history_path, cfg_history_path):
        align = ['left', 'left', 'left', 'right', 'center']
        header = ['Name', 'Path', 'Source', 'Size', 'Modified']
        time_fmt = '%Y-%m-%d %H:%M'

        table = [[
            TableCell(h, h, 0, i, align[i], bold=True)
            for i, h in enumerate(header)
            ]]
        paths = [
            ('Configuration', config_path, False),
            ('History database', history_path, bool(cfg_history_path))
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
        term_color = RimaDiffCli.terminal_color
        if errs:
            print(
                term_color('black', fg='red') + '\n'.join(errs)
                + term_color() + '\n'
                )

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


def main():
    dirs = PlatformDirs(PurePath(__file__).stem, False)
    data_path = dirs.user_data_path

    config_path = _ensure_config(dirs)
    config = _read_config(config_path)

    cfg_history_path = config.get('history_path')
    history_path = _get_history_db_path(dirs, cfg_history_path)

    setup_names = list(config['user-setup'])

    api_url = config['api_url']
    user_setup = {
        name: UserSetup(setup) for name, setup in config['user-setup'].items()}

    history_manager = HistoryManager(history_path)
    cli = RimaDiffCli(api_url, user_setup, history_manager)

    args = _parse_arguments(setup_names)
    setup_name = args.user_setup or 'default'

    if args.list_history:
        cli.list_history()
        return
    elif args.list_users:
        cli.list_users(setup_name)
        return
    elif args.list_paths:
        cli.list_paths(config_path, history_path, cfg_history_path)
        return

    print_skills = args.skills or args.all_tables
    print_xp = args.xp or args.all_tables
    print_skill_rank = args.skill_rank or args.all_tables
    print_activities = args.activities or args.all_tables
    print_activity_rank = args.activity_rank or args.all_tables
    if not (print_skills or print_xp or print_skill_rank
            or print_activities or print_activity_rank):
        print_skills = True

    cli.print_tables(
        setup_name, args.force_download, args.difference,
        print_skills, print_xp, print_skill_rank,
        print_activities, print_activity_rank
        )


def _ensure_config(dirs):
    config_path = dirs.place_config_file('rimadiff.toml')
    if not config_path.is_file():
        default_path = Path(__file__).parent / 'default_config.toml'
        with (default_path.open('rb') as default_config,
            config_path.open('wb') as new_config):
            # Write new default config
            new_config.write(default_config.read())
        print(f'\nWrote new configuration file in\n  {config_path}')
    return config_path


def _get_history_db_path(dirs, cfg_history_path):
    if cfg_history_path:
        return Path(cfg_history_path).expanduser().resolve()
    history_path = dirs.place_data_file('history.db')
    return history_path


def _read_config(config_path):
    with config_path.open('rb') as fp:
        config = tomllib.load(fp)
    return config


def _parse_arguments(setup_names):
    parser = argparse.ArgumentParser(
        prog='rimadiff',
        description=(
            'Compare OSRS game hiscores in terminal. If none of the '
            'table choice flags are given, -s is assumed.'
            )
        )
    parser.add_argument(
        '-u', '--user-setup', metavar='NAME', choices=setup_names,
        help='name of user setup, using "default" if not given'
        )
    parser.add_argument(
        '-f', '--force-download', action='store_true',
        help='do not skip downloading if done today already'
        )
    parser.add_argument(
        '-d', '--difference', action='store_true',
        help='RIMA is absolute, others shown as arithmetic difference'
        )
    parser.add_argument(
        '-s', '--skills', action='store_true',
        help='print skill level table'
        )
    parser.add_argument(
        '-x', '--xp', action='store_true',
        help='print skill experience table'
        )
    parser.add_argument(
        '-r', '--skill-rank', action='store_true',
        help='print skill rank table'
        )
    parser.add_argument(
        '-a', '--activities', action='store_true',
        help='print activities table'
        )
    parser.add_argument(
        '-R', '--activity-rank', action='store_true',
        help='print activity rank table'
        )
    parser.add_argument(
        '-A', '--all-tables', action='store_true',
        help='print all tables. Same as -s -x -r -a -R'
        )
    parser.add_argument(
        '-l', '--list-history', action='store_true',
        help='list history snapshots'
        )
    parser.add_argument(
        '-U', '--list-users', action='store_true',
        help='list information on the users'
        )
    parser.add_argument(
        '-p', '--list-paths', action='store_true',
        help='list paths used by the script'
        )
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    main()
