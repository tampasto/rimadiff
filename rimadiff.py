import argparse
import json
import math
import sqlite3
import tomllib
import urllib.parse
from collections import Counter
from datetime import date, datetime, UTC
from numbers import Number
from pathlib import Path

import requests


CONFIG_PATH = '~/.config/rimadiff.toml'

DEFAULT_CONFIG = '''
api_url = 'https://secure.runescape.com/m=hiscore_oldschool/index_lite.json?player={}'
history_path = '~/.rimadiff_history.db'

[user-setup.default]
users = ['Faux', 'Manked', 'Mote Plox', 'Mr Mammal']
user_alias = {'Manked' = 'PKer', 'Mote Plox' = 'Historian'}
rima = 'Faux'
'''


class UserSetup:
    def __init__(self, setup):
        self.users = setup['users']
        self.user_alias = setup['user_alias']
        self.rima = setup['rima']


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
    }

    @classmethod
    def terminal_color(self, bg=None, bold=False, fg='white'):
        if bg is None:
            return '\033[m'
        bold_def = ('1;' if bold else '')
        bg_def = self.TERMINAL_COLORS[bg]
        fg_def = self.TERMINAL_COLORS[fg] - 10
        return f'\033[{bold_def}{bg_def};{fg_def}m'

    def __init__(self, api_url, history_path, user_setup):
        self.api_url = api_url
        self.history_manager = HistoryManager(history_path)
        self.user_setup = user_setup

        self._users = None
        self._user_alias = None
        self._rima = None
        self._force_download = False
        self._show_difference = False

        self._download_success_users = []
        self._download_fail_users = []
        self._download_fail_errors = Counter()
        self._bad_json_users = []

    def print_tables(
        self, setup_name, force_download, show_difference,
        print_skills, print_xp, print_skill_rank,
        print_activities, print_activity_rank
    ):
        self._users = self.user_setup[setup_name].users
        self._user_alias = self.user_setup[setup_name].user_alias
        self._rima = self.user_setup[setup_name].rima

        self._force_download = force_download
        self._show_difference = show_difference
        self.history_manager.open_connection()

        err = None
        user_data = na_users = None
        now = datetime.now().astimezone()
        try:
            user_data, na_users, user_history_time = self._source_user_data(now)
            category_tables = self._build_tables(user_data, na_users, now)
        except Exception as error:
            err = error
        finally:
            self.history_manager.close_connection()
        if err:
            raise err

        print()

        dl_success = self._download_success_users
        if len(dl_success):
            print('Downloaded: ' + ', '.join(dl_success) + '\n')

        dl_fail = self._download_fail_users
        term_color = RimaDiffCli.terminal_color
        if len(dl_fail):
            print(
                term_color('red')
                + 'Could not download: ' + ', '.join(dl_fail)
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
                + 'Bad API JSON: ' + ', '.join(json_fail)
                + term_color() + '\n'
                )

        if len(user_history_time):
            print('Fetched at', end='')
            if len(set(user_history_time.values())) == 1:
                time, timezone = next(iter(user_history_time.values()))
                print(f' {time} {timezone}\n')
            else:
                variable_tz = len(set(t[1] for t in user_history_time.values())) > 1
                _, timezone = next(iter(user_history_time.values()))
                print(('' if variable_tz else f' ({timezone})'))
                sorted_items = sorted(
                    user_history_time.items(), key=lambda item: item[1][0])
                for user, (time, timezone) in sorted_items:
                    print(
                        time + (f' ({timezone})' if variable_tz else '')
                        + f' {user}'
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
            self._print_table(table, hide_if_zero, comp_rank)


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
                    data, category_labels, official_name = self._download_data(user, session)
                    if data is not None:
                        self.history_manager.write_data(
                            today_ordinal, user_id, data, category_labels,
                            now_time, now_timezone
                            )
                        self.history_manager.update_official_name(user_id, official_name)
                push_to_dict(data, user, user_id)

            for user in new_users:
                data, category_labels, official_name = self._download_data(user, session)
                user_id = None
                if data is not None:
                    user_id = self.history_manager.add_user(
                        user, official_name)
                    self.history_manager.write_data(
                        today_ordinal, user_id, data, category_labels,
                        now_time, now_timezone
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
        user_official_name = self.history_manager.get_user_official_name_dict()
        for user in self._users:
            col_header = user_official_name.get(user, user)

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
                    label = self.history_manager.get_label(
                        category, label_id, today_ordinal, user)
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
        official_name = None
        quoted_user = urllib.parse.quote(user, safe='')
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

        if resp:
            self._download_success_users.append(user)
            obj = resp.json()
            data, category_labels, official_name = self._response_json_to_data(obj)
            if data is None:
                self._bad_json_users.append(user)
        return data, category_labels, official_name

    def _response_json_to_data(self, obj):
        official_name = obj['name']

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
        return data, category_labels, official_name

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
        base = 0.25 * (levels['Defence'] + levels['Hitpoints'] + levels['Prayer']//2)
        melee = levels['Attack'] + levels['Strength']
        ranged = levels['Ranged'] * 3 // 2
        mage = levels['Magic'] * 3 // 2
        combat_level = math.floor(base + 0.325 * max(melee, ranged, mage))
        return combat_level

    def _print_table(self, table, hide_if_zero, comp_rank):
        rima_col_i = -1
        try:
            rima_col_i = table[0].index('RIMA', 1)
        except ValueError:
            pass

        text_table = []
        for row_i, row in enumerate(table):
            text_row = []
            for col_i, val in enumerate(row):
                text = str(val)
                if isinstance(val, Number):
                    if self._show_difference and col_i != rima_col_i:
                        rima_val = table[row_i][rima_col_i]
                        if isinstance(rima_val, Number):
                            val = val - rima_val
                            table[row_i][col_i] = val
                            text = ('+' if val > 0 else '') + f'{val:,}'.replace(',', ' ')
                        else:
                            table[row_i][col_i] = 0
                            text = 'n/a'
                    else:
                        text = f'{val:,}'.replace(',', ' ')
                text_row.append(text)
            text_table.append(text_row)

        lens = [max(map(len, col_text)) for col_text in zip(*text_table)]

        term_color = RimaDiffCli.terminal_color
        row_num = 0
        for row_i, row in enumerate(text_table):
            orig_row = table[row_i]
            if hide_if_zero and all(v == 0 or v == '-' for v in orig_row[1:]):
                continue

            header_row = (row_i == 0)
            row_bg = ('black' if row_num % 2 == 0 else 'darkgray')
            for col_i, text in enumerate(row):
                bold = (header_row or col_i == 0)
                bg = row_bg
                fg = 'white'
                val = table[row_i][col_i]

                # Highlight RIMA
                if col_i == rima_col_i:
                    if header_row:
                        bg = 'orange'
                    else:
                        fg = 'orange'

                elif col_i > 0 and isinstance(val, Number):
                    rima_val = table[row_i][rima_col_i]
                    comp_val = (0 if self._show_difference else rima_val)
                    if isinstance(comp_val, Number):
                        if comp_rank:
                            val, comp_val = comp_val, val
                        if val > comp_val:
                            fg = 'green'
                            bold = True
                        elif val < comp_val:
                            fg = 'red'

                color_def = term_color(bg, bold, fg)
                print(f'{color_def} {text:>{lens[col_i]}} ', end='')
            print(term_color())
            row_num += 1
        print()

    def list_history(self):
        self.history_manager.open_connection()
        snapshots = self.history_manager.get_history_snapshots()
        print()
        for snapshot_i, (date_ordinal, time, timezone) in enumerate(snapshots):
            date_obj = date.fromordinal(date_ordinal)
            num = len(snapshots) - snapshot_i
            print(f'[{num}] {date_obj} {time} {timezone}')
        print()
        self.history_manager.close_connection()


class HistoryManager:
    DB_SCHEMA = """
        CREATE TABLE Label (
            category INT, -- 0: Skill level, 1: Skill xp, 2: Skill rank, 3: Activity, 4: Activity rank
            id INT,
            version INT,
            value TEXT NOT NULL,
            PRIMARY KEY (category, id, version)
        ) STRICT, WITHOUT ROWID;

        CREATE TABLE User (
            id INT PRIMARY KEY,
            user TEXT NOT NULL UNIQUE,
            official_name TEXT
        ) STRICT, WITHOUT ROWID;

        CREATE TABLE UserDataTime (
            date_ordinal INT,
            user_id INT REFERENCES User (id) ON DELETE CASCADE,
            time TEXT NOT NULL, -- Local time as HH:MM
            timezone TEXT NOT NULL, -- As +HHMM
            PRIMARY KEY (date_ordinal, user_id)
        ) STRICT, WITHOUT ROWID;

        CREATE TABLE UserData (
            date_ordinal INT, -- Proleptic Gregorian ordinal, 0001-01-01 is 1, etc.
            user_id INT,
            label_category INT,
            label_id INT,
            label_version INT NOT NULL,
            value INT NOT NULL,
            PRIMARY KEY (date_ordinal, user_id, label_category, label_id),
            FOREIGN KEY (date_ordinal, user_id)
                REFERENCES UserDataTime (date_ordinal, user_id) ON DELETE CASCADE,
            FOREIGN KEY (label_category, label_id, label_version)
                REFERENCES Label (category, id, version) ON DELETE CASCADE
        ) STRICT, WITHOUT ROWID;
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = None
        self.cursor = None

    def open_connection(self):
        write_schema = not self.db_path.exists()
        self.db = sqlite3.connect(self.db_path)
        self.cursor = self.db.cursor()
        cur = self.cursor
        cur.execute('PRAGMA foreign_keys = ON')
        if write_schema:
            schema = HistoryManager.DB_SCHEMA
            schema = '\n'.join(ln[8:] for ln in schema.split('\n'))
            cur.executescript(schema)

    def close_connection(self):
        self.cursor.close()
        self.db.close()

    def sort_users(self, users_set):
        """Sort db users_set for UserData pk considerations."""
        user_id = self.get_user_id_dict()
        db_users = sorted([(user_id[u], u) for u in users_set if u in user_id])
        new_users = sorted([u for u in users_set if u not in user_id])
        return db_users, new_users

    def read_data(self, date_ordinal, user_id):
        # data[category][label_id] = value
        cur = self.cursor
        cur.arraysize = 300
        cur.execute(
            'SELECT label_category, label_id, value '
            'FROM UserData WHERE date_ordinal = ? AND user_id = ?',
            (date_ordinal, user_id)
            )
        rows = cur.fetchall()
        if len(rows) == 0:
            return None, None, None
        max_category = max(r[0] for r in rows)
        data = []
        for category in range(max_category+1):
            label_values = {
                id_: value for cat, id_, value in rows if cat == category}
            data.append(label_values)
        cur.arraysize = 1
        cur.execute(
            'SELECT time, timezone FROM UserDataTime '
            'WHERE date_ordinal = ? AND user_id = ?',
            (date_ordinal, user_id)
            )
        time, timezone = self._fetch_row(cur, 2)
        return data, time, timezone

    def write_data(
        self, date_ordinal, user_id, data, category_labels, time, timezone
    ):
        # data[category][label_id] = value
        # category_labels[category][label_id] = label
        cur = self.cursor
        data_rows = []
        # category_labels[category][label_id] = version
        versions = []
        for category in range(len(data)):
            versions.append([None] * len(data[category]))
        for category, label_values in enumerate(category_labels):
            for label_id, label in enumerate(label_values):
                version = self._get_label_version(category, label_id, label)
                if version is None:
                    version = self._add_label_version(
                        category, label_id, label)
                versions[category][label_id] = version

        for category, label_values in enumerate(data):
            for label_id, value in enumerate(label_values):
                label_version = versions[category][label_id]
                row = (
                    date_ordinal, user_id, category, label_id,
                    label_version, value
                    )
                data_rows.append(row)
        self._remove_extra_data(date_ordinal, user_id, data_rows)
        cur.execute(
            'INSERT INTO UserDataTime (date_ordinal, user_id, time, timezone) '
            'VALUES (?, ?, ?, ?)'
            'ON CONFLICT (date_ordinal, user_id) '
            'DO UPDATE SET time = excluded.time, timezone = excluded.timezone',
            (date_ordinal, user_id, time, timezone)
            )
        cur.executemany(
            'INSERT INTO UserData ('
                'date_ordinal, user_id, label_category, label_id, '
                'label_version, value'
            ') VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT (date_ordinal, user_id, label_category, label_id) '
            'DO UPDATE SET value = excluded.value',
            data_rows
            )
        self.db.commit()

    def _remove_extra_data(self, date_ordinal, user_id, data_rows):
        # data_rows[] = (date_ordinal, user_id, category, label_id, ...)
        cur = self.cursor
        cur.arraysize = 300
        cur.execute(
            'SELECT label_category, label_id '
            'FROM UserData WHERE date_ordinal = ? AND user_id = ?',
            (date_ordinal, user_id)
            )
        category_label_ids = cur.fetchall()
        extra = []
        for category, label_id in category_label_ids:
            if not any(r for r in data_rows
                    if r[2] == category and r[3] == label_id):
                extra.append((date_ordinal, user_id, category, label_id))
        if extra:
            cur.executemany(
                'DELETE FROM UserData '
                'WHERE date_ordinal = ? AND user_id = ? '
                    'AND label_category = ? AND label_id = ?',
                extra
                )
            self.db.commit()

    def update_official_name(self, user_id, official_name):
        cur = self.cursor
        cur.execute(
            'UPDATE User SET official_name = ? WHERE id = ?',
            (official_name, user_id)
            )
        self.db.commit()

    def _get_label_version(self, category, label_id, label):
        cur = self.cursor
        cur.arraysize = 1
        cur.execute(
            'SELECT version FROM Label '
            'WHERE category = ? AND id = ? AND value = ?',
            (category, label_id, label)
            )
        return self._fetch_row(cur)

    def _add_label_version(self, category, label_id, label):
        cur = self.cursor
        version = self._column_increment(
            'Label', 'version', ('category', 'id'), (category, label_id))
        cur.execute(
            'INSERT INTO Label (category, id, version, value) VALUES (?, ?, ?, ?)',
            (category, label_id, version, label)
            )
        self.db.commit()
        return version

    def add_user(self, user, official_name):
        cur = self.cursor
        user_id = self._column_increment('User', 'id')
        cur.execute(
            'INSERT INTO User (id, user, official_name) VALUES (?, ?, ?)',
            (user_id, user, official_name)
            )
        self.db.commit()
        return user_id

    def _column_increment(self, table, column, filters=None, values=()):
        cur = self.cursor
        cur.arraysize = 1
        filter_sql = ''
        if filters:
            filter_sql = (
                ' WHERE ' + ' AND '.join(f'{col} = ?' for col in filters))
        cur.execute(f'SELECT Max({column}) FROM {table}{filter_sql}', values)
        max_value = cur.fetchone()[0]
        value = 0
        if max_value is not None:
            value = max_value + 1
        return value

    def get_user_official_name_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT user, official_name FROM User')
        user_official_name = dict(cur.fetchall())
        return user_official_name

    def get_user_id_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT user, id FROM User')
        user_id = dict(cur.fetchall())
        return user_id

    def get_label(self, category, label_id, date_ordinal, user):
        cur = self.cursor
        cur.arraysize = 1
        cur.execute(
            'SELECT L.value '
            'FROM User AS U '
            'INNER JOIN UserData AS D ON U.user = ? AND U.id = D.user_id '
            'INNER JOIN Label AS L '
                'ON D.date_ordinal = ? AND D.user_id = D.user_id '
                'AND D.label_category = ? AND D.label_id = ?'
                'AND D.label_category = L.category AND D.label_id = L.id '
                'AND D.label_version = L.version',
            (user, date_ordinal, category, label_id)
            )
        return self._fetch_row(cur)

    def _fetch_row(self, cur, columns=1):
        row = cur.fetchone()
        if row is None:
            if columns == 1:
                return None
            else:
                return tuple([None] * columns)
        elif columns == 1:
            return row[0]
        return row

    def get_history_snapshots(self):
        cur = self.cursor
        cur.arraysize = 300
        cur.execute(
            'SELECT DISTINCT date_ordinal, time, timezone FROM UserDataTime')
        snapshots = cur.fetchall()
        return snapshots


def main():
    config = _read_config()
    setup_names = list(config['user-setup'])
    args = _parse_arguments(setup_names)

    api_url = config['api_url']
    history_path_str = config['history_path']
    history_path = Path(history_path_str).expanduser().resolve()
    user_setup = {
        name: UserSetup(setup) for name, setup in config['user-setup'].items()}
    cli = RimaDiffCli(api_url, history_path, user_setup)

    if args.list_history:
        cli.list_history()
        return

    setup_name = args.user_setup or 'default'

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


def _read_config():
    config_path = Path(CONFIG_PATH).expanduser().resolve()
    config_path.parent.mkdir(exist_ok=True)
    if not config_path.exists():
        with config_path.open('w', encoding='utf-8') as fp:
            fp.write(DEFAULT_CONFIG.lstrip())

    with config_path.open('rb') as fp:
        config = tomllib.load(fp)
    return config


def _parse_arguments(setup_names):
    parser = argparse.ArgumentParser(
        prog='rimadiff',
        description=(
            'Compare OSRS game hiscores in terminal. If none of table '
            'choice flags are given, -s is assumed.'
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
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    main()
