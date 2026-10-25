import argparse


def parse_arguments(setup_names):
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
