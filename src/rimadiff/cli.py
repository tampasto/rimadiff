from rimadiff.config_reader import ConfigReader
from rimadiff.history_manager import HistoryManager
from rimadiff.renderer import Renderer

import click
from click import secho


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
@click.option('-d', '--difference', is_flag=True,
    help='RIMA is absolute, others shown as arithmetic difference')
@click.option('-t', '--table', multiple=True, help='Select tables')
@click.pass_context
def cli(ctx, user_setup, force_download, difference, table):
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

    show_table = _parse_table_names(ctx, table)
    if show_table is None:
        ctx.exit(2)

    # If no tables, show skill
    if all((not f) for f in show_table.values()):
        show_table['skill'] = True

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

    history_manager = HistoryManager(config.history_path)
    renderer = Renderer(config, history_manager)

    renderer.print_tables(user_setup, force_download, difference, show_table)


def _parse_table_names(ctx, table):
    long_name = {
        's': 'skill', 'x': 'xp', 'r': 'skill-rank',
        'a': 'activity', 'c': 'activity-rank'
        }
    show_table = {n: False for n in long_name.values()}
    if table is None:
        return show_table

    msgs = []
    if len(table) == 1 and table[0] in show_table:
        show_table[table[0]] = True
    elif len(table) == 1 and table[0] == 'every':
        _flag_tables('long', table, show_table, long_name, msgs)
    elif len(table) == 1:
        _flag_tables('short', table[0], show_table, long_name, msgs)
    else:
        _flag_tables('long', table, show_table, long_name, msgs)
    if msgs:
        msgs.insert(0, ctx.get_usage())
        click.echo('\n\n'.join(msgs))
        return None
    return show_table


def _flag_tables(len_, names, show_table, long_name, msgs):
    no_table = []
    for nm in names:
        name = (nm if len_ == 'long' else long_name.get(nm))
        if name in show_table:
            show_table[name] = True
        elif name == 'every' or nm == 'e':
            for n in show_table:
                show_table[n] = True
        else:
            no_table.append(nm)
    if no_table:
        msgs.append(_err_format(len_, no_table, names, long_name))


def _err_format(len_, no_table, orig, long_name):
    valid = ' '.join(long_name.values())
    if len_ == 'short':
        np = 'table argument'
        vals = repr(orig)
        valid = ' '.join(long_name) + f'\nValid long names: {valid}'
    else:
        np = f'long table name'
        if len(no_table) != 1:
            np += 's'
        vals = ', '.join(repr(n) for n in no_table)
    return (
        f'Error: No such {np} {vals}.\n'
        f'Valid {len_} names: {valid}'
        )


@cli.command()
def history():
    """List history snapshots."""
    config = ConfigReader()
    config.ensure_config()
    config.read()

    history_manager = HistoryManager(config.history_path)
    renderer = Renderer(config, history_manager)
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

    history_manager = HistoryManager(config.history_path)
    renderer = Renderer(config, history_manager)
    renderer.list_users(user_setup)


@cli.command()
def path():
    """List paths used by the script."""
    config = ConfigReader()
    config.ensure_config()
    config.read()

    history_manager = HistoryManager(config.history_path)
    renderer = Renderer(config, history_manager)
    renderer.list_paths()
