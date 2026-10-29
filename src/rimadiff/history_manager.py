import sqlite3
from contextlib import AbstractContextManager
from pathlib import PurePath

from rimadiff.category import Category


class HistoryManager(AbstractContextManager):
    CATEGORIES = (
        Category('skill', 0, 'Skill level'),
        Category('xp', 1, 'Skill xp'),
        Category('skill-rank', 2, 'Skill rank'),
        Category('activity', 3, 'Activity'),
        Category('activity-rank', 4, 'Activity rank')
        )
    SCHEMA_PATH = PurePath(__file__).parent / 'history_schema.sql'

    def __init__(self, db_path):
        self.db_path = db_path
        self.db = None
        self.cursor = None

    def __enter__(self):
        self.open()
        return self

    def open(self):
        write_schema = not self.history_exists()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(self.db_path)
        self.cursor = self.db.cursor()
        cur = self.cursor
        cur.execute('PRAGMA foreign_keys = ON')
        if write_schema:
            sql = self._get_schema()
            cur.executescript(sql)

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self):
        self.cursor.close()
        self.db.close()

    def history_exists(self):
        return self.db_path.exists()

    def _get_schema(self):
        category_comment = ', '.join(
            f'{c.category}: {c.header}' for c in HistoryManager.CATEGORIES)
        with open(type(self).SCHEMA_PATH, 'r', encoding='utf-8') as fp:
            sql = fp.read().format(category_comment=category_comment)
        return sql

    def sort_users(self, users_set):
        """Sort db users for UserData pk considerations."""
        user_id = self.get_user_id_dict()
        db_users = sorted([(user_id[u], u) for u in users_set if u in user_id])
        new_users = sorted([u for u in users_set if u not in user_id])
        return db_users, new_users

    def read_data(self, date_ordinal, user_ids, categories):
        # user_db_data[user_id][category][label_id] = value
        # user_history_time[user_id] = (time, timezone)
        in_ = self._in_with_placeholders
        sql_data = (
            'SELECT user_id, label_category, label_id, value '
            'FROM UserData '
            f'WHERE date_ordinal = ? AND user_id {in_(user_ids)} '
                f'AND label_category {in_(categories)}'
            )
        ph_data = (date_ordinal, *user_ids, *categories)
        rows_data = self._query_all(sql_data, ph_data, arraysize=300)
        if len(rows_data) == 0:
            return {}, {}

        user_db_data = {}
        for user_id in user_ids:
            cat_dict = {}
            for category in categories:
                label_values = {
                    id_: value
                    for u_id, cat, id_, value in rows_data
                    if u_id == user_id and cat == category
                    }
                cat_dict[category] = label_values
            user_db_data[user_id] = cat_dict

        sql_time = (
            'SELECT R.user_id, U.name, R.time, R.timezone '
            'FROM UserDataRequest AS R '
            'LEFT JOIN User AS U ON R.user_id = U.id '
            f'WHERE R.date_ordinal = ? AND R.user_id {in_(user_ids)}'
            )
        ph_time = (date_ordinal, *user_ids)
        rows_time = self._query_all(sql_time, ph_time, arraysize=30)

        user_history_time = {}
        for user_id in user_ids:
            time = timezone = None
            row = next((r for r in rows_time if r[0] == user_id), None)
            if row:
                _, username, time, timezone = row
            user_history_time[username] = time, timezone
        return user_db_data, user_history_time

    def write_data(self, time_tuple, downloaded):
        # downloaded: APIResponse[]
        # r.data             [category] [label_id] = value
        # versions [user_id] [category] [label_id] = version

        date_ordinal, time, timezone = time_tuple

        versions = self._get_label_versions_add_new(downloaded, date_ordinal)

        # New user_id values are already added to User
        data_rows = []
        for resp in downloaded:
            for category, label_values in resp.data.items():
                for label_id, value in label_values.items():
                    label_version = versions[resp.user_id][category][label_id]
                    row = (
                        date_ordinal, resp.user_id, category, label_id,
                        label_version, value
                        )
                    data_rows.append(row)

        user_ids = [r.user_id for r in downloaded]
        self._remove_redundant_data_rows(date_ordinal, user_ids, data_rows)

        cur = self.cursor
        request_rows = [
            (date_ordinal, resp.user_id, time, timezone, resp.url)
            for resp in downloaded
            ]
        cur.executemany(
            'INSERT INTO UserDataRequest ('
                'date_ordinal, user_id, time, timezone, url'
            ') '
            'VALUES (?, ?, ?, ?, ?)'
            'ON CONFLICT (date_ordinal, user_id) '
            'DO UPDATE SET '
                'time = excluded.time, '
                'timezone = excluded.timezone, '
                'url = excluded.url',
            request_rows
            )
        cur.executemany(
            'INSERT INTO UserData ('
                'date_ordinal, user_id, label_category, label_id, '
                'label_version, value'
            ') VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT (date_ordinal, user_id, label_category, label_id) '
            'DO UPDATE SET '
                'label_version = excluded.label_version, '
                'value = excluded.value',
            data_rows
            )
        self.db.commit()

    def _get_label_versions_add_new(self, downloaded, date_ordinal):
        # downloaded: APIResponse[]
        # r.labels           [category] [label_id] = label
        # versions [user_id] [category] [label_id] = version

        versions = {}
        for c in HistoryManager.CATEGORIES:
            category = c.category
            id_version = {}
            id_label_version = self._get_id_label_version_dict(category)
            for resp in downloaded:
                user_id = resp.user_id
                versions.setdefault(user_id, {})
                versions[user_id].setdefault(category, {})

                label_values = resp.labels[category]
                for label_id, label in label_values.items():
                    version = None
                    try:
                        version = id_label_version[label_id][label]
                    except KeyError:
                        version = self._add_label_version(
                            category, label_id, label, date_ordinal)
                        id_label_version.setdefault(label_id, {})
                        id_label_version[label_id][label] = version
                    versions[user_id][category][label_id] = version
        return versions

    def _get_id_label_version_dict(self, category):
        sql = (
            'SELECT id, value, version '
            'FROM Label '
            'WHERE category = ?'
            )
        rows = self._query_all(sql, (category,), arraysize=300)

        id_label_version = {}
        for id_, label, version in rows:
            id_label_version.setdefault(id_, {})
            id_label_version[id_][label] = version
        return id_label_version

    def _add_label_version(self, category, label_id, label, date_ordinal):
        cur = self.cursor
        version = self._column_increment(
            'Label', 'version', ('category', 'id'), (category, label_id))
        cur.execute(
            'INSERT INTO Label ('
                'category, id, version, value, added_date_ordinal) '
            'VALUES (?, ?, ?, ?, ?)',
            (category, label_id, version, label, date_ordinal)
            )
        self.db.commit()
        return version

    def _remove_redundant_data_rows(self, date_ordinal, user_ids, new_rows):
        # new_rows[] = (date_ordinal, user_id, category, label_id, ...)
        in_ = self._in_with_placeholders
        sql = (
            'SELECT user_id, label_category, label_id '
            'FROM UserData '
            f'WHERE date_ordinal = ? AND user_id {in_(user_ids)}'
            )
        ph = (date_ordinal, *user_ids)
        old_rows = self._query_all(sql, ph, arraysize=1000)

        extra = []
        for user_id, category, label_id in old_rows:
            if not any(r for r in new_rows
                if r[1] == user_id and r[2] == category and r[3] == label_id):
                # Does not exist in new dataset, so plain UPSERT would
                # leave it dangling
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

    def add_user(self, user, user_original, date_ordinal):
        cur = self.cursor
        user_id = self._column_increment('User', 'id')
        cur.execute(
            'INSERT INTO User (id, name, name_original, added_date_ordinal) '
            'VALUES (?, ?, ?, ?)',
            (user_id, user, user_original, date_ordinal)
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

    def get_label_dict(self, users, date_ordinal, categories):
        # label_dict = label_dict[category][label_id] = label
        label_dict = {n: {} for n in categories}

        # Get every (category, label_id) for all users on specified date
        in_ = self._in_with_placeholders

        sql_cat_id = (
            'SELECT DISTINCT D.label_category, D.label_id '
            'FROM User AS U '
            'LEFT JOIN UserData AS D '
                f'ON U.name {in_(users)} AND D.date_ordinal = ? '
                f'AND U.id = D.user_id AND D.label_category {in_(categories)} '
            )
        ph_cat_id = (*users, date_ordinal, *categories)
        cat_id = self._query_all(sql_cat_id, ph_cat_id, arraysize=300)

        # Get label versions preferring first users
        user_id_dict = self.get_user_id_dict()
        sql_label = (
            'SELECT L.id, L.value '
            'FROM UserData AS D '
            'INNER JOIN Label AS L '
                'ON D.date_ordinal = ? AND D.user_id = ? '
                'AND D.label_category = ? AND D.label_id IN ({id_sql}) '
                'AND D.label_category = L.category AND D.label_id = L.id '
                'AND D.label_version = L.version '
            )
        for user in users:
            user_id = user_id_dict[user]
            left_to_query = [
                (category, label_id)
                for category, label_id in cat_id
                if label_dict[category].get(label_id) is None
                ]
            if not left_to_query:
                break

            query_categories = sorted(set(r[0] for r in left_to_query))
            for category in query_categories:
                category_dict = label_dict[category]

                label_ids = sorted(
                    r[1] for r in left_to_query if r[0] == category)
                id_sql = ', '.join('?' * len(label_ids))
                sql = sql_label.format(id_sql=id_sql)

                pc_label = (date_ordinal, user_id, category, *label_ids)

                label_rows = self._query_all(sql, pc_label)

                for label_id, label in label_rows:
                    category_dict[label_id] = label

        return label_dict

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

    def _query_all(self, sql, placeholders, *, arraysize=None):
        cur = self.cursor
        if arraysize is not None:
            cur.arraysize = arraysize
        cur.execute(sql, placeholders)
        rows = cur.fetchall()
        return rows

    def _in_with_placeholders(self, values):
        return 'IN (' + ', '.join('?' * len(values)) + ')'

    def get_history_snapshots(self):
        sql = (
            'SELECT DISTINCT date_ordinal, time, timezone '
            'FROM UserDataRequest'
            )
        rows = self._query_all(sql, (), arraysize=300)

        snapshots = []
        ordinals = sorted({r[0] for r in rows})
        for date_ordinal in ordinals:
            snapshots.append((
                date_ordinal,
                [(r[1], r[2]) for r in rows if r[0] == date_ordinal]
                ))
        return snapshots

    def get_info_users(self):
        cur = self.cursor
        cur.arraysize = 50
        cur.execute(
            'SELECT Max(U.name), Max(U.name_original), Count(R.date_ordinal) '
            'FROM User AS U '
            'LEFT JOIN UserDataRequest AS R ON U.id = R.user_id '
            'GROUP BY U.id'
            )
        counts = cur.fetchall()
        cur.execute(
            'WITH latest AS ( '
                'SELECT '
                    'U.id, Max(U.name) AS username, '
                    'Max(R1.date_ordinal) AS date_ordinal '
                'FROM User AS U '
                'LEFT JOIN UserDataRequest AS R1 ON U.id = R1.user_id '
                'GROUP BY U.id '
            ') '
            'SELECT L.username, L.date_ordinal, R2.time, R2.timezone '
            'FROM latest AS L '
            'LEFT JOIN UserDataRequest AS R2 '
                'ON L.id = R2.user_id AND L.date_ordinal = R2.date_ordinal'
            )
        latest_snapshot = cur.fetchall()
        return counts, latest_snapshot

