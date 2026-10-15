import argparse
import json
import math
import numbers
import tomllib
import urllib.parse
from datetime import datetime, UTC
from pathlib import Path

import requests


CONFIG_PATH = '~/.config/rimadiff.toml'

DEFAULT_CONFIG = '''
api_url = 'https://secure.runescape.com/m=hiscore_oldschool/index_lite.json?player={}'
history_path = '~/.rimadiff_history'

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

    def __init__(self, api_url, history_path, user_setup, setup_name):
        self.api_url = api_url
        self.history_path = history_path

        self.users = user_setup[setup_name].users
        self.user_alias = user_setup[setup_name].user_alias
        self.rima = user_setup[setup_name].rima
        self._force_download = False
        self._show_relative = False

    def print_tables(
        self, force_download, show_relative,
        print_skills, print_xp, print_activities
    ):
        self._force_download = force_download
        self._show_relative = show_relative
        self.history_path.mkdir(parents=True, exist_ok=True)

        skills = []
        activities = []

        dl_user = []
        tables = self._get_tables(dl_user, skills, activities)
        table_skill_level, table_skill_xp, table_activity = tables
        if len(dl_user):
            print('\nDownloaded: ' + ', '.join(dl_user))

        print()
        self._add_combat_level(table_skill_level)
        tables = []
        if print_skills:
            tables.append((table_skill_level, False))
        if print_xp:
            tables.append((table_skill_xp, False))
        if print_activities:
            tables.append((table_activity, True))
        for table, hide_if_zero in tables:
            self._print_table(table, hide_if_zero)


    def _get_tables(self, dl_user, skills, activities):
        user_obj = {}
        with requests.Session() as session:
            for user in self.users:
                obj = self._get_object(user, dl_user, session)
                for skill_obj in obj['skills']:
                    if skill_obj['name'] not in skills:
                        skills.append(skill_obj['name'])
                for act_obj in obj['activities']:
                    if act_obj['name'] not in activities:
                        activities.append(act_obj['name'])
                user_obj[user] = obj

        table_skill_level = [['Skill'], *([skill] for skill in skills)]
        table_skill_xp = [['Skill'], *([skill] for skill in skills)]
        table_activity = [['Activity'], *([act] for act in activities)]
        for user in self.users:
            obj = user_obj[user]
            show_user = user

            # Nayta dorkalle RIMA
            if user == self.rima:
                show_user = 'RIMA'

            elif user in self.user_alias:
                show_user = self.user_alias[user]

            table_skill_level[0].append(show_user)
            table_skill_xp[0].append(show_user)
            for skill_i, skill in enumerate(skills):
                level, xp = 0, 0
                obj_skill = next((s for s in obj['skills'] if s['name'] == skill), None)
                if obj_skill:
                    level, xp = obj_skill['level'], obj_skill['xp']
                table_skill_level[skill_i + 1].append(level)
                table_skill_xp[skill_i + 1].append(xp)

            table_activity[0].append(show_user)
            for activity_i, activity in enumerate(activities):
                score = 0
                obj_act = next((a for a in obj['activities'] if a['name'] == activity), None)
                if obj_act:
                    score = obj_act['score']
                table_activity[activity_i + 1].append(score)

        return table_skill_level, table_skill_xp, table_activity

    def _get_object(self, user, dl_user, session):
        utc_date = datetime.now(tz=UTC).date().isoformat()
        path = self.history_path / f'{user}/{utc_date}.json'
        path.parent.mkdir(exist_ok=True)
        obj = None
        if self._force_download or not path.exists():
            url = self.api_url.format(urllib.parse.quote(user, safe=''))
            resp = session.get(url)
            obj = resp.json()
            path.write_text(resp.text, encoding='utf-8')
            dl_user.append(user)
        else:
            obj = json.loads(path.read_text(encoding='utf-8'))
        return obj

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

    def _print_table(self, table, hide_if_zero):
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
                if isinstance(val, numbers.Number):
                    if self._show_relative and col_i != rima_col_i:
                        rima_val = table[row_i][rima_col_i]
                        if isinstance(rima_val, numbers.Number):
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
            if hide_if_zero and max(orig_row[1:]) == 0:
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

                elif col_i > 0 and isinstance(val, numbers.Number):
                    rima_val = table[row_i][rima_col_i]
                    comp_val = (0 if self._show_relative else rima_val)
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


def main():
    config = _read_config()
    setup_names = list(config['user-setup'])
    args = _parse_arguments(setup_names)

    api_url = config['api_url']
    history_path_str = config['history_path']
    user_setup = {
        name: UserSetup(setup) for name, setup in config['user-setup'].items()}
    setup_name = args.user_setup or 'default'

    history_path = Path(history_path_str).expanduser().resolve()

    cli = RimaDiffCli(api_url, history_path, user_setup, setup_name)

    print_skills = args.skills or args.all_tables
    print_xp = args.xp or args.all_tables
    print_activities = args.activities or args.all_tables
    if not (print_skills or print_xp or print_activities):
        print_skills = True

    cli.print_tables(
        args.force_download, args.show_relative,
        print_skills, print_xp, print_activities
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
        '-r', '--show-relative', action='store_true',
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
        '-a', '--activities', action='store_true',
        help='print activities table'
        )
    parser.add_argument(
        '-A', '--all-tables', action='store_true',
        help='print all tables. Same as -s -x -a'
        )
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    main()
