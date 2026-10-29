from rimadiff.config_reader import ConfigReader
from rimadiff.renderer import Renderer

import click


@click.group(
    invoke_without_command=True,
    context_settings={'help_option_names': ['-h', '--help']}
    )
@click.option('-s', '--user-setup', default='default',
    metavar='NAME', envvar='RIMADIFF_USER_SETUP',
    help='Name of user setup, using "default" if not given'
    )
@click.option('-f', '--force-download', is_flag=True,
    help='Do not skip downloading if done today already')
@click.option('-t', '--table', multiple=True, help='Select tables')
@click.pass_context
def cli(ctx, user_setup, force_download, table):
    """
    Compare OSRS game hiscores in terminal.

    The base command prints tables for the selected user setup.

    If no tables are selected, "skill" table will be shown.

    Table names have two forms: the short and the long form. Either one
    picks the same table. For example tables "s" and "skill" are the
    same. You can pick more than one table. Short names are written as
    one word after the -t flag, e.g. "-t sx" to select "skill" and "xp".
    The space after -t is optional. Long forms can be used by using the
    --table option multiple times. You cannot mix both short and long
    table names in the same invocation.

    If the table name ends with "-diff" or is upper case for short
    forms, then RIMA is absolute and other users are shown as arithmetic
    difference. In other words, for skill levels the table names would
    be "S" or "skill-diff".

    \b
    Table names:
    s, skill ........ Skill levels
    x, xp ........... Experience
    r, skill-rank ... Skill level rankings
    a, activity ..... Activities
    c, activity-rank  Activity rankings
    e, every ........ Shorthand for every table above

    To avoid rewriting the user setup for every call, it can be given in
    the shell environment variable RIMADIFF_USER_SETUP.
    """
    if ctx.invoked_subcommand is not None:
        return

    table_names = _parse_table_names(ctx, table)
    if table_names is None:
        ctx.exit(2)

    # If no tables, show skill
    if len(table_names) == 0:
        table_names.append('skill')

    config = ConfigReader()
    config.ensure_config()
    config.read()
    is_valid, valid_names = config.check_user_setup(user_setup)
    if not is_valid:
        click.echo(
            ctx.get_usage()
            + f'\n\nError: No such user setup {user_setup!r}.\n'
            f"Current setups: {', '.join(valid_names)}"
            )
        return

    renderer = Renderer(config)

    renderer.print_tables(user_setup, force_download, table_names)


def _parse_table_names(ctx, args):
    if args is None:
        return []

    long_name = {
        's': 'skill', 'x': 'xp', 'r': 'skill-rank',
        'a': 'activity', 'c': 'activity-rank'
        }
    long_name_e = long_name.copy()
    long_name_e['e'] = 'every'
    long_name_list = list(long_name.values())
    valid_long = long_name_list + [f'{n}-diff' for n in long_name_list]
    valid_long_e = valid_long.copy()
    valid_long_e += ['every', 'every-diff']

    msgs = []
    table_names = []
    use_short = False
    if len(args) == 1:
        arg = args[0]
        if arg in valid_long:
            return [arg]
        if arg not in ('every', 'every-diff'):
            _flag_tables(
                'short', arg, table_names, long_name_e, long_name_list, msgs)
            use_short = True

    if not use_short:
        _flag_tables(
            'long', args, table_names, valid_long_e, long_name_list, msgs)
    if msgs:
        msgs.insert(0, ctx.get_usage())
        click.echo('\n\n'.join(msgs))
        return None
    return table_names


def _flag_tables(len_, names, table_names, valid, long_name_list, msgs):
    no_table = []
    for nm in names:
        name = nm
        if len_ == 'short':
            name = valid.get(nm.lower())
            if not name:
                no_table.append(name)
                continue
            if nm.upper() == nm:
                name += '-diff'
        elif name not in valid:
            no_table.append(name)
            continue

        if name == 'every':
            table_names.extend(long_name_list)
        elif name == 'every-diff':
            table_names.extend(f'{n}-diff' for n in long_name_list)
        else:
            table_names.append(name)
    if no_table:
        msgs.append(_err_format(len_, no_table, names, valid))


def _err_format(len_, no_table, orig, valid):
    if len_ == 'short':
        np = 'table argument'
        vals = repr(orig)
        valid_text += (
            ' '.join(valid) + ' '
            + ' '.join(c.upper() for c in valid)
            + f'\nValid long names: ' + ' '.join(valid.values())
            )
    else:
        valid_text = ' '.join(valid)
        np = f'long table name'
        if len(no_table) != 1:
            np += 's'
        vals = ', '.join(repr(n) for n in no_table)
    return (
        f'Error: No such {np} {vals}.\n'
        f'Valid {len_} names: {valid_text}'
        )


@cli.command()
def history():
    """List history snapshots."""
    config = ConfigReader()
    config.ensure_config()
    config.read()

    renderer = Renderer(config)
    renderer.list_history()


@cli.command()
@click.option('-s', '--user-setup', default='default',
    metavar='NAME', envvar='RIMADIFF_USER_SETUP',
    help='Name of user setup, using "default" if not given')
def user(user_setup):
    """List information on the users."""
    config = ConfigReader()
    config.ensure_config()
    config.read()

    renderer = Renderer(config)
    renderer.list_users(user_setup)


@cli.command()
def path():
    """List paths used by the script."""
    config = ConfigReader()
    config.ensure_config()
    config.read()

    renderer = Renderer(config)
    renderer.list_paths()
