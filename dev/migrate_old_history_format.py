"""
Migrate old JSON file directory-based format to new SQLite format.

"""


import json
import sys
from datetime import date, datetime
from pathlib import Path

from rimadiff.rimadiff import RimaDiffCli, _read_config
from rimadiff.history_manager import HistoryManager

DEFAULT_OLD_HISTORY_PATH = '~/.rimadiff_history'


def main(argv):
    config = _read_config()
    history_path = Path(config['history_path']).expanduser().resolve()

    old_path = Path(DEFAULT_OLD_HISTORY_PATH)
    if len(argv) > 1:
        old_path = Path(argv[1])
    old_path = old_path.expanduser().resolve()

    rdc = RimaDiffCli(None, history_path, None)
    hm = rdc.history_manager
    print(f'\nFrom {old_path}')
    print(f'To   {hm.db_path}')
    print(f"\n\"From\" is {'' if old_path.is_dir() else 'NOT '}directory.")
    if input('\nConfirm? (y/n) ').lower() != 'y':
        quit()
    print()

    hm.open_connection()
    err = None
    try:
        _migrate_data(old_path, hm, rdc)
    except Exception as error:
        err = error
    finally:
        hm.close_connection()
    if err is not None:
        raise err


def _migrate_data(old_path, hm, rdc):
    user_id_dict = hm.get_user_id_dict()
    bad_json_users = []
    imported_ordinals = set()
    imported_users = set()

    for user_dir in old_path.iterdir():
        for file_path in user_dir.iterdir():
            date_obj = date.fromisoformat(file_path.stem)
            date_ordinal = date_obj.toordinal()

            obj = None
            with file_path.open('r', encoding='utf-8') as fp:
                obj = json.load(fp)
            data, category_labels, user_response = (
                rdc._response_json_to_data(obj))
            if data is None:
                bad_json_users.append(f'{user_dir.name} {file_path.stem}')
                continue

            user = user_response.lower()
            user_id = user_id_dict.get(user)
            if user_id is None:
                user_id = hm.add_user(user, user_response)
                user_id_dict[user] = user_id

            stat_mtime = file_path.stat().st_mtime
            mtime = datetime.fromtimestamp(stat_mtime).astimezone()
            time = mtime.time().isoformat()[:5]
            timezone = mtime.strftime('%z')

            hm.write_data(
                date_ordinal, user_id, data, category_labels,
                time, timezone, ''
                )
            imported_ordinals.add(date_ordinal)
            imported_users.add(user_response)

    if len(bad_json_users):
        print('Bad JSON:\n  ' + '\n  '.join(bad_json_users)) + '\n'
    print('Imported users:')
    for user_response in sorted(imported_users):
        print(f'  {user_response}')
    print('\nImported snapshot dates:')
    for ordinal in sorted(imported_ordinals):
        print(f'  {date.fromordinal(ordinal)} - ordinal: {ordinal}')
    print()


if __name__ == '__main__':
    main(sys.argv)
