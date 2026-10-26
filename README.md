# rimadiff
Compare OSRS game hiscores in terminal.

The CLI can display comparison tables for

* Skill levels
* Skill experiences
* Skill ranks
* Activity scores
* Activity ranks

There is a special username defined as RIMA which will be the focus of
comparison. RIMA is highlighted and it is possible to calculate relative
differences against this user. Setting up RIMA username is optional.

The application uses a configuration file and stores all fetched
historical data in an [SQLite](https://sqlite.org/) database file in the
user data directory. An alternate database path can also be defined in
the config.

The datasets will not be refetched by default again for the same day
unless forced to do so.

The default username setup of the configuration file looks like this:

```toml
[user-setup.default]
users = ['Faux', 'Manked', 'Mote Plox', 'Mr Mammal']
user_alias = {'Manked' = 'PKer', 'Mote Plox' = 'Historian'}
rima = 'Faux'
```

This means that username Faux is RIMA. Users Manked and Mote Plox have
aliases PKer and Historian respectively. The alias is shown in the tables
instead of their real usernames. Aliases are optional. User Mr Mammal
will be displayed with their real username. The configuration file
follows [TOML format](https://toml.io/en/).

You may add multiple user setups by adding more `[user-setup.SETUP_NAME]`
tables. The only required key is `users`, the others can be left out.

## Installing
Clone or download the repository first. Examples are given for pip and
uv setups.

The following example commands are for Linux systems.

Both examples below will create a virtual environment to directory .venv
and install the project dependencies plus the project as an editable
install.

### pip install
File `requirements.txt` is provided for convenience to easily install
dependencies with pip. It is strongly advised to set up a virtual
environment.

```bash
cd /path/to/rimadiff
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### uv install

There are no special considerations in the virtual environment with uv
as it will set it up automatically when `rimadiff` is run for the first
time. If you want to create the venv in a separate command, you may run
`uv sync` in the project directory.

[Install Astral uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
# If you already have uv, update it (example for .sh script install)
uv self update
```

### Running the tool

```bash
# pip setup
source /path/to/rimadiff/.venv/bin/activate
python3 -m rimadiff

# uv setup
uv run --project /path/to/rimadiff rimadiff
```

You may want to create an alias for the command in your `.bashrc` or
`.bash_aliases` file.

```bash
alias rimadiff='uv run --project /path/to/rimadiff rimadiff'
alias rimadiff='source /path/to/rimadiff/.venv/bin/activate && python3 -m rimadiff'
```

When `rimadiff` is run for the first time, it creates a new
configuration file in the
[platform-specific directory](https://platformdirs.readthedocs.io/en/latest/platforms.html)
under the directory "rimadiff". When the base command is run for
printing the tables, it will also download the hiscores for the users
defined in the configuration from the
[Old School Hiscores API](https://runescape.wiki/w/Application_programming_interface#Old_School_Hiscores).

In other words, it is recommended to first prepare the config user list
before printing any tables. You can find the path to the configuration
file by running the the following command.

```bash
rimadiff path
```

See all command line options with `rimadiff -h`.

If you choose to use multiple user setups, you can reference the setup
in the command line option --user-setup (-s) for each `rimadiff`
invocation or define an environment variable for the shell session.

```bash
export RIMADIFF_USER_SETUP=swedish-noobs
```

There are multiple ways to refer to the tables to print. If no tables
are given, `skill` table is inferred. To print both the experience table
and skill ranking table, you can use any of the following commands.

```bash
rimadiff --table xp --table skill-rank
rimadiff -t xp -t skill-rank
rimadiff --table xr
rimadiff -t xr
```

If you only want to see the skill ranking table, you can type

```bash
rimadiff -t skill-rank
rimadiff -t r
# Or if you are REAAALLY lazy
rimadiff -tr
```

The one letter short names for tables can be found on the help page
`rimadiff -h`.
