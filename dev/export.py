import json
import sqlite3
import sys
import textwrap
from datetime import date
from pathlib import Path


def main():
    src, dest = sys.argv[1:]
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    category_dict = {
        0: ('skills', 'level'),
        1: ('skills', 'xp'),
        2: ('skills', 'rank'),
        3: ('activities', 'score'),
        4: ('activities', 'rank'),
        }

    with sqlite3.connect(src) as con:
        cur = con.cursor()
        cur.arraysize = 1000
        sql = _fmt('''
        SELECT
            U.name_original,
            R.date_ordinal,
            concat(R.time, R.timezone),
            R.url,
            L.category,
            L.value,
            D.value
        FROM User AS U
        INNER JOIN UserDataRequest AS R
            ON U.id = R.user_id
        INNER JOIN UserData AS D
            ON R.date_ordinal = D.date_ordinal
            AND R.user_id = D.user_id
        INNER JOIN Label AS L
            ON D.label_category = L.category
            AND D.label_id = L.id
            AND D.label_version = L.version
        ORDER BY
            U.name_original, R.date_ordinal, R.time, L.id, L.category
        ''')

        path = None
        obj = None
        label_cat_id = None
        user_set = set()
        ss_set = set()
        last_user = None
        last_ordinal = None

        row_iter = cur.execute(sql)
        for user, ordinal, time, url, category, label, value in row_iter:
            if last_user != user or last_ordinal != ordinal:
                _write_data(path, obj)

                dt = date.fromordinal(ordinal)
                path = dest / user / f'{dt} {time}.json'
                label_cat = sorted(
                    {l for l, _ in category_dict.values()}, reverse=True)
                obj = {'name': user, 'url': url, **{l: [] for l in label_cat}}
                label_cat_id = {l: 0 for l in label_cat}

            field1, field2 = category_dict[category]
            if len(obj[field1]) > 0 and obj[field1][-1]['name'] == label:
                subobj = obj[field1][-1]
            else:
                id_ = label_cat_id[field1]
                subobj = {'id': id_, 'name': label}
                label_cat_id[field1] += 1
                obj[field1].append(subobj)
            subobj[field2] = value

            user_set.add(user)
            ss_set.add(ordinal)
            last_user = user
            last_ordinal = ordinal

        _write_data(path, obj)

        if len(user_set) == 0:
            user_set.add('n/a')
        ss_str = 'n/a'
        if len(ss_set) > 0:
            ss_str = (
                str(date.fromordinal(min(ss_set))) + ' .. '
                + str(date.fromordinal(max(ss_set)))
                + f' ({len(ss_set)})'
                )
        print(
            '\nExported users:\n  ' + ', '.join(sorted(user_set))
            + '\n\nExported snapshots:\n  ' + ss_str + '\n'
            )


def _write_data(path, obj):
    if not path:
        return
    path.parent.mkdir(exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(obj, fp, allow_nan=False, separators=(',', ':'))


def _fmt(sql):
    return textwrap.dedent(sql).strip()


if __name__ == '__main__':
    main()
