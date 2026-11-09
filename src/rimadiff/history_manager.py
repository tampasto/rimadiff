import math
import sqlite3
import textwrap
from collections import namedtuple
from contextlib import AbstractContextManager
from itertools import chain, islice, repeat
from pathlib import Path

from rimadiff.categories import (
    api_categories, data_categories, label_categories)


class HistoryManager(AbstractContextManager):
    SCHEMA_FILE = 'history_schema.sql'

    # CONTEXT MANAGER

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = None
        self.cursor = None

    def __enter__(self):
        self.open()
        return self

    def open(self):
        write_schema = not self.db_path.exists()

        self.db = sqlite3.connect(self.db_path)
        self.cursor = self.db.cursor()
        cur = self.cursor
        cur.execute('PRAGMA foreign_keys = ON')
        if write_schema:
            path = Path(__file__).parent / HistoryManager.SCHEMA_FILE
            with path.open('r', encoding='utf-8') as fp:
                sql = fp.read()
            cur.executescript(sql)

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self):
        self.cursor.close()
        self.db.close()

    # DATA READING

    def read_data(self, date_ordinal, user_ids, data_cat_ids):
        # user_data [user_id] [data_category_id] [label] = value
        in_ = self._in_with_placeholders
        sql = self._format_sql(f'''
            SELECT S.user_id, D.data_category, L.name, D.value
            FROM Snapshot AS S
            INNER JOIN Data AS D
                ON S.date_ordinal = ?
                AND S.user_id {in_(user_ids)}
                AND S.id = D.snapshot
                AND D.data_category {in_(data_cat_ids)}
            LEFT JOIN Label AS L ON D.label = L.id
            ''')
        ph = (date_ordinal, *user_ids, *data_cat_ids)
        rows_iter = self._query_iter(sql, ph)
        user_data = self._rows_to_dict(rows_iter)
        return user_data

    def get_user_api_id(self, date_ordinal, user_ids):
        # user_api_id [user_id] = api_category_id
        in_ = self._in_with_placeholders
        sql = self._format_sql(f'''
            SELECT user_id, api_category
            FROM Snapshot
            WHERE date_ordinal = ? AND user_id {in_(user_ids)}
            ''')
        ph = (date_ordinal, *user_ids)
        rows = self._query_all(sql, ph, arraysize=20)
        user_api_id = dict(rows)
        return user_api_id

    def read_data_time(self, date_ordinal, user_ids):
        # user_history_time[user] = (time, timezone)
        in_ = self._in_with_placeholders
        sql = self._format_sql(f'''
            SELECT U.name, S.time, S.timezone
            FROM Snapshot AS S
            INNER JOIN User AS U
                ON S.date_ordinal = ?
                AND S.user_id {in_(user_ids)}
                AND S.user_id = U.id
            ''')
        ph = (date_ordinal, *user_ids)
        row_iter = self._query_iter(sql, ph)

        user_history_time = {}
        for user, time, timezone in row_iter:
            user_history_time[user] = time, timezone
        return user_history_time

    def _get_snapshot_id_dict(self, date_ordinal):
        snapshot_id_dict = {}
        sql = 'SELECT user_id, id FROM Snapshot WHERE date_ordinal = ?'
        ph = (date_ordinal,)
        rows = self._query_all(sql, ph, arraysize=30)
        snapshot_id_dict = dict(rows)
        return snapshot_id_dict

    def get_history_snapshots(self):
        sql = self._format_sql('''
            SELECT DISTINCT date_ordinal, time, timezone
            FROM Snapshot
            ''')
        rows = self._query_all(sql, arraysize=300)

        snapshots = []
        ordinals = sorted({r[0] for r in rows})
        for date_ordinal in ordinals:
            time_list = []
            for ordinal, time, timezone in rows:
                if ordinal != date_ordinal:
                    continue
                time_list.append((time, timezone))
            snapshots.append((date_ordinal, time_list))
        return snapshots

    def get_info_users(self):
        count_cols = ('user', 'user_display', 'snapshot_count')
        CountRow = namedtuple('CountRow', count_cols)
        counts_sql = self._format_sql('''
            SELECT Max(U.name), Max(U.display), Count(S.date_ordinal)
            FROM User AS U
            INNER JOIN Snapshot AS S ON U.id = S.user_id
            GROUP BY U.id
            ''')
        count_rows = self._query_all(counts_sql, arraysize=50)
        counts = [CountRow(*r) for r in count_rows]

        latest_cols = (
            'user', 'date_ordinal', 'time', 'timezone', 'api_cat_id')
        LatestRow = namedtuple('LatestRow', latest_cols)
        latest_snapshot_sql = self._format_sql('''
            WITH latest AS (
                SELECT
                    U.id AS user_id,
                    Max(U.name) AS user_name,
                    Max(S1.date_ordinal) AS date_ordinal
                FROM User AS U
                INNER JOIN Snapshot AS S1 ON U.id = S1.user_id
                GROUP BY U.id
            )
            SELECT
                L.user_name, L.date_ordinal, S2.time, S2.timezone,
                S2.api_category
            FROM latest AS L
            LEFT JOIN Snapshot AS S2
                ON L.user_id = S2.user_id
                AND L.date_ordinal = S2.date_ordinal
            ''')
        latest_rows = self._query_all(latest_snapshot_sql)
        latest_snapshot = [LatestRow(*r) for r in latest_rows]

        return counts, latest_snapshot

    # DATA WRITING

    def write_data(self, time_tuple, downloaded, *, update_info=True):
        # downloaded: APIResponse[]
        # r.data [data_category_id] [label] = value
        # label_id_dict [label_category_id] [label] = label_id

        date_ordinal, time, timezone = time_tuple

        (label_id_dict, update_display, update_position
            ) = self._ensure_label_id(downloaded, date_ordinal)

        if update_info:
            self._update_label('display', update_display)
            self._update_label('position', update_position)

        data_label_cat = {
            dc.id: dc.label_category.id for dc in data_categories}
        snapshot_id_dict = self._get_snapshot_id_dict(date_ordinal)

        # New user_id values are already added to User
        data_rows = []
        for resp in sorted(downloaded, key=lambda r: r.user_id):
            user_id, api_id = resp.user_id, resp.api_id
            url, data = resp.url, resp.data

            snapshot_id = snapshot_id_dict.get(user_id)
            if not snapshot_id:
                snapshot_id = self._add_snapshot(
                    date_ordinal, user_id, api_id, time, timezone, url)
            else:
                self._update_snapshot(api_id, snapshot_id, time, timezone, url)

            for data_cat_id, label_values in data.items():
                label_values = data[data_cat_id]
                for label, value in label_values.items():
                    label_cat_id = data_label_cat[data_cat_id]
                    label_id = label_id_dict[label_cat_id][label]
                    row = (snapshot_id, label_id, data_cat_id, value)
                    data_rows.append(row)

        existing_ss_ids = sorted(snapshot_id_dict.values())
        should_vacuum = False
        if existing_ss_ids:
            self._remove_old_snapshot_data(snapshot_id_dict)
            should_vacuum = True

        cur = self.cursor
        insert_sql = self._format_sql('''
            INSERT INTO Data (snapshot, label, data_category, value)
            VALUES
            ''')
        row_ph = '(?, ?, ?, ?)'

        snapshot_len = math.ceil(len(data_rows) / len(downloaded))
        row_iter = iter(data_rows)
        while rows := islice(row_iter, snapshot_len):
            row_list = list(rows)
            if not row_list:
                break
            sql = (
                insert_sql + '\n  '
                + ',\n  '.join(repeat(row_ph, len(row_list)))
                )
            ph = tuple(chain(*row_list))
            cur.execute(sql, ph)
        self.db.commit()
        return should_vacuum

    def _remove_old_snapshot_data(self, existing_ss_ids):
        # new_rows[] = (snapshot_id, label_id, data_cat_id, value)
        in_ = self._in_with_placeholders
        del_sql = self._format_sql(f'''
            DELETE FROM Data
            WHERE snapshot {in_(existing_ss_ids)}
            ''')
        self.cursor.execute(del_sql, tuple(existing_ss_ids))
        self.db.commit()

    def _add_snapshot(
        self, date_ordinal, user_id, api_cat_id, time, timezone, url
    ):
        sql = self._format_sql('''
            INSERT INTO Snapshot (
                date_ordinal, user_id, api_category, time, timezone, url
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ''')
        ph = (date_ordinal, user_id, api_cat_id, time, timezone, url)
        self.cursor.execute(sql, ph)
        self.db.commit()
        return self.cursor.lastrowid

    def _update_snapshot(
        self, api_cat_id, snapshot_id, time, timezone, url
    ):
        sql = self._format_sql('''
            UPDATE Snapshot
            SET api_category = ?, time = ?, timezone = ?, url = ?
            WHERE id = ?
            ''')
        ph = (api_cat_id, time, timezone, url, snapshot_id)
        self.cursor.execute(sql, ph)
        self.db.commit()

    # LABEL READING

    def get_label_dict(self, users, date_ordinal):
        # label_dict = label_dict[label_category_id][label] = display
        # -> Innermost dict is ordered by position
        in_ = self._in_with_placeholders

        sql = self._format_sql(f'''
            SELECT L.label_category, L.name, L.display, L.position
            FROM User AS U
            INNER JOIN Snapshot AS S
                ON U.name {in_(users)}
                AND U.id = S.user_id
                AND S.date_ordinal = ?
            INNER JOIN Data AS D ON S.id = D.snapshot
            INNER JOIN Label AS L ON D.label = L.id
            ORDER BY L.label_category
            ''')
        ph = (*users, date_ordinal)
        row_iter = self._query_iter(sql, ph)

        label_dict = {}
        label_pos_dict = {}
        display_dict = None
        position_dict = None
        last_cat_id = None
        for label_cat_id, label, display, position in row_iter:
            if display_dict is None:
                display_dict = {}
                position_dict = {}
            elif label_cat_id != last_cat_id:
                label_dict[last_cat_id] = display_dict
                display_dict = {}
                label_pos_dict[last_cat_id] = position_dict
                position_dict = {}

            display_dict[label] = display
            position_dict[label] = position
            last_cat_id = label_cat_id
        label_dict[last_cat_id] = display_dict
        label_pos_dict[last_cat_id] = position_dict

        return label_dict, label_pos_dict

    # LABEL WRITING

    def _ensure_label_id(self, downloaded, date_ordinal):
        # downloaded: APIResponse[]
        # r.labels       [label_category_id] [label] = (display, position)
        # labels_current [label_category_id] [label] = (id, display, position)
        # label_id_dict  [label_category_id] [label] = label_id

        labels_current = {}
        for label_cat in label_categories:
            label_info = {}
            sql = self._format_sql('''
                SELECT name, id, display, position
                FROM Label
                WHERE label_category = ?
                ''')
            ph = (label_cat.id,)
            for label, id_, display, position in self._query_iter(sql, ph):
                label_info[label] = (id_, display, position)
            labels_current[label_cat.id] = label_info

        label_id_dict = {lc.id: {} for lc in label_categories}
        update_display = set()
        update_position = set()
        for resp in downloaded:
            for label_cat_id, resp_dict in resp.labels.items():
                lidict = {}
                for label, (display, position) in resp_dict.items():
                    try:
                        cur_tuple = labels_current[label_cat_id][label]
                    except KeyError:
                        id_ = self._add_label(
                            label_cat_id, label, display, position,
                            date_ordinal
                            )
                        new_tuple = id_, display, position
                        labels_current[label_cat_id][label] = new_tuple
                    else:
                        id_, cur_display, cur_position = cur_tuple
                        if display != cur_display:
                            update_display.add((display, id_))
                        if position != cur_position:
                            update_position.add((position, id_))
                    lidict[label] = id_

                label_id_dict.setdefault(label_cat_id, {})
                label_id_dict[label_cat_id].update(lidict)

        return label_id_dict, update_display, update_position

    def _add_label(self, label_cat_id, label, display, position, date_ordinal):
        cur = self.cursor
        sql = self._format_sql('''
            INSERT INTO Label (
                label_category, name, display, position, added_date_ordinal)
            VALUES (?, ?, ?, ?, ?)
            ''')
        ph = (label_cat_id, label, display, position, date_ordinal)
        cur.execute(sql, ph)
        self.db.commit()
        return cur.lastrowid

    def _update_label(self, col_name, update_ph):
        if not update_ph:
            return
        sql = f'UPDATE Label SET {col_name} = ? WHERE id = ?'
        self.cursor.executemany(sql, update_ph)
        self.db.commit()

    # USER

    def get_user_id_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT name, id FROM User')
        user_id_dict = dict(cur.fetchall())
        return user_id_dict

    def get_user_display_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT name, display FROM User')
        user_display_dict = dict(cur.fetchall())
        return user_display_dict

    def get_user_added_date_ordinal_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT name, added_date_ordinal FROM User')
        user_added_dict = dict(cur.fetchall())
        return user_added_dict

    def add_user(self, user, user_display, date_ordinal):
        cur = self.cursor
        sql = self._format_sql('''
            INSERT INTO User (name, display, added_date_ordinal)
            VALUES (?, ?, ?)
            ''')
        ph = (user, user_display, date_ordinal)
        cur.execute(sql, ph)
        self.db.commit()
        return cur.lastrowid

    def update_user_display(self, user_id, user_display):
        cur = self.cursor
        cur.execute(
            'UPDATE User SET display = ? WHERE id = ?',
            (user_display, user_id)
            )
        self.db.commit()

    # CATEGORIES

    def ensure_label_data_category_ids(self):
        self._ensure_label_category_ids()
        self._ensure_data_category_ids()

    def _ensure_label_category_ids(self):
        sql = f'SELECT name, id FROM LabelCategory'
        rows = self._query_all(sql, arraysize=2)
        id_dict = dict(rows)
        for cat in label_categories:
            id_ = id_dict.get(cat.name)
            if not id_:
                id_ = self._add_category(
                    'LabelCategory', cat.name, cat.display)
            cat.id = id_

    def _ensure_data_category_ids(self):
        sql = f'SELECT name, label_category, id FROM DataCategory'
        rows = self._query_all(sql, arraysize=5)
        for cat in data_categories:
            match_tuple = cat.name, cat.label_category.id
            try:
                row = next(r for r in rows if r[:2] == match_tuple)
            except StopIteration:
                extra = {'label_category': cat.label_category.id}
                id_ = self._add_category(
                    'DataCategory', cat.name, cat.display, extra)
            else:
                id_ = row[2]
            cat.id = id_

    def ensure_api_category_ids(self, api_names=None):
        if len(api_categories) == 0:
            # No API URL config, no can do
            return

        in_ = self._in_with_placeholders
        sql = 'SELECT name, id FROM APICategory'
        ph = ()
        if api_names:
            sql += f'\nWHERE name {in_(api_names)}'
            ph = tuple(api_names)
            names = api_names
        rows = self._query_all(sql, ph)
        if not api_names:
            names = [r[0] for r in rows]

        id_dict = dict(rows)
        api_cats = sorted(
            (next(c for c in api_categories if c.name == n)
            for n in names),
            key=lambda c: api_categories.index(c)
            )
        for api_cat in api_cats:
            id_ = id_dict.get(api_cat.name)
            if not id_:
                id_ = self._add_category(
                    'APICategory', api_cat.name, api_cat.display)
            api_cat.id = id_

    def _add_category(self, table, name, display, extra={}):
        dep_col = ', '.join([*extra, ''])
        dep_ph = ', '.join([*('?'*len(extra)), ''])
        sql = self._format_sql(f'''
            INSERT INTO {table} ({dep_col}name, display)
            VALUES ({dep_ph}?, ?)
            ''')
        ph = (*extra.values(), name, display)
        cur = self.cursor
        cur.execute(sql, ph)
        self.db.commit()
        return cur.lastrowid

    # GENERAL DATABASE

    def vacuum(self):
        self.cursor.execute('VACUUM')

    # SQL UTILITIES

    def _format_sql(self, sql):
        return textwrap.dedent(sql).strip()

    def _in_with_placeholders(self, values):
        return 'IN (' + ', '.join('?' * len(values)) + ')'

    def _query_iter(self, sql, placeholders=(), *, arraysize=1):
        cur = self.cursor
        if arraysize is not None:
            cur.arraysize = arraysize
        row_iter = cur.execute(sql, placeholders)
        return row_iter

    def _query_all(self, sql, placeholders=(), *, arraysize=None):
        self._query_iter(sql, placeholders, arraysize=arraysize)
        rows = self.cursor.fetchall()
        return rows

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

    def _rows_to_dict(self, rows_iter):
        row_dict = {}
        for row in rows_iter:
            col_penultimate = len(row) - 2
            col_dict = row_dict
            for col_i, val in enumerate(row):
                if col_i == col_penultimate:
                    col_dict[val] = row[-1]
                    break
                else:
                    col_dict.setdefault(val, {})
                    col_dict = col_dict[val]
        return row_dict
