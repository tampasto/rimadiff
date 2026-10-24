import sqlite3
from pathlib import PurePath


class HistoryManager:
    SCHEMA_PATH = PurePath(__file__).parent / 'history_schema.sql'

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
            sql = None
            with open(type(self).SCHEMA_PATH, 'r', encoding='utf-8') as fp:
                sql = fp.read()
            cur.executescript(sql)

    def close_connection(self):
        self.cursor.close()
        self.db.close()

    def sort_users(self, users_set):
        """Sort db users for UserData pk considerations."""
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
            'SELECT time, timezone FROM UserDataRequest '
            'WHERE date_ordinal = ? AND user_id = ?',
            (date_ordinal, user_id)
            )
        time, timezone = self._fetch_row(cur, 2)
        return data, time, timezone

    def write_data(
        self, date_ordinal, user_id, data, category_labels,
        time, timezone, url
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
            'INSERT INTO UserDataRequest ( '
                'date_ordinal, user_id, time, timezone, url '
            ') '
            'VALUES (?, ?, ?, ?, ?)'
            'ON CONFLICT (date_ordinal, user_id) '
            'DO UPDATE SET time = excluded.time, timezone = excluded.timezone',
            (date_ordinal, user_id, time, timezone, url)
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

    def update_user_original(self, user_id, user_original):
        cur = self.cursor
        cur.execute(
            'UPDATE User SET name_original = ? WHERE id = ?',
            (user_original, user_id)
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
            'INSERT INTO Label (category, id, version, value) '
            'VALUES (?, ?, ?, ?)',
            (category, label_id, version, label)
            )
        self.db.commit()
        return version

    def add_user(self, user, user_original):
        cur = self.cursor
        user_id = self._column_increment('User', 'id')
        cur.execute(
            'INSERT INTO User (id, name, name_original) VALUES (?, ?, ?)',
            (user_id, user, user_original)
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

    def get_user_original_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT name, name_original FROM User')
        user_original_dict = dict(cur.fetchall())
        return user_original_dict

    def get_user_id_dict(self):
        cur = self.cursor
        cur.arraysize = 100
        cur.execute('SELECT name, id FROM User')
        user_id_dict = dict(cur.fetchall())
        return user_id_dict

    def get_label(self, category, label_id, date_ordinal, user_id):
        cur = self.cursor
        cur.arraysize = 1
        cur.execute(
            'SELECT L.value '
            'FROM UserData AS D '
            'INNER JOIN Label AS L '
                'ON D.date_ordinal = ? AND D.user_id = ? '
                'AND D.label_category = ? AND D.label_id = ? '
                'AND D.label_category = L.category AND D.label_id = L.id '
                'AND D.label_version = L.version',
            (date_ordinal, user_id, category, label_id)
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
            'SELECT DISTINCT date_ordinal, time, timezone FROM UserDataRequest')
        snapshots = cur.fetchall()
        return snapshots

    def get_info_users(self):
        cur = self.cursor
        cur.arraysize = 50
        cur.execute(
            'SELECT U.name_original, U.name, Count(R.date_ordinal) '
            'FROM User AS U '
            'LEFT JOIN UserDataRequest AS R ON U.id = R.user_id '
            'GROUP BY R.user_id'
            )
        counts = cur.fetchall()
        cur.execute(
            'WITH latest AS ( '
                'SELECT U.id, U.name, Max(R1.date_ordinal) AS date_ordinal '
                'FROM User AS U '
                'LEFT JOIN UserDataRequest AS R1 ON U.id = R1.user_id '
                'GROUP BY R1.user_id '
            ') '
            'SELECT L.name, R2.date_ordinal, R2.time, R2.timezone '
            'FROM latest AS L '
            'LEFT JOIN UserDataRequest AS R2 '
                'ON L.id = R2.user_id AND L.date_ordinal = R2.date_ordinal'
            )
        latest_snapshot = cur.fetchall()
        return counts, latest_snapshot

