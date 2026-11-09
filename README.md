# rimadiff
Compare OSRS game hiscores in terminal.

The CLI displays colour-judged comparison tables for

* Skill levels
* Skill experiences
* Skill ranks
* Activity scores
* Activity ranks

The source data is downloaded from the
[Old School RuneScape Hiscore APIs](https://runescape.wiki/w/Application_programming_interface#Old_School_Hiscores).

There is a special username defined as RIMA which will be the focus of
comparison. RIMA is highlighted and it is possible to calculate relative
differences against this user. Setting up RIMA username is optional.

The application uses TOML configuration files and stores all fetched
historical data in an [SQLite](https://sqlite.org/) database file. All
paths are configurable as environment variables. Colours and styles of
the printed tables are completely customizable in the colour
configuration and multiple colour schemes are supported. API URLs can be
edited in a separate configuration file if they were to change or if
other APIs with similar JSON responses were to be used.

The datasets will not be refetched by default again for the same day
unless forced to do so.

The default username setup of the configuration file looks like this:

```toml
users = ['Faux', 'Manked', 'Mote Plox', 'Mr Mammal', 'Herbiboar']
rima = 'Faux'
user_alias = {'Manked' = 'PKer', 'Mote Plox' = 'Historian'}
default_api = 'main'
user_api = {'Herbiboar' = 'ultimate'}
```

This means that username Faux is RIMA. Users Manked and Mote Plox have
aliases PKer and Historian respectively. The alias is shown in the
tables instead of their real usernames. Aliases are optional. The
`default_api` definition is a no-op as Main account API is the default
anyways.  This will be the default API for all users, if not specified
otherwise in the key `user_api`. User Herbiboar is an ultimate ironman
and their results are downloaded from the respective API. Rank colouring
is not applied for users from a different API.

For the configuration file syntax, see the
[TOML guide](https://toml.io/en/).

You may add multiple user setups by adding more
`[user-setup.SETUP_NAME]` tables. The only required key is `users`, the
others can be left out.

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
alias rimadiff='. /path/to/rimadiff/.venv/bin/activate && python3 -m rimadiff'
```

When the base command `rimadiff` is run for the first time, it writes
new default configuration files in the
[platform-specific directories](https://platformdirs.readthedocs.io/en/latest/platforms.html)
under the directory "rimadiff". The directories are config and data.

If you wish to use custom locations for your config and/or history
database file, define the shell environment variables in your `.bashrc`.
The paths must be writable. For example:

```bash
export RIMADIFF_CONFIG_DIR=~/.rimadiff_config
export RIMADIFF_HISTORY_PATH=~/.rimadiff_history.db
```

When the base command is run for printing the tables, it will also
download the hiscores for the users defined in the configuration if the
database or a snapshot for today does not yet exist.

In other words, it is recommended to first prepare the config user list
before printing any tables. You can find the path to the configuration
file by running the the following command. None of the subcommands write
any files except "init-config".

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
rimadiff -txr
```

To print the arithmetic differences for each user with respect to RIMA,
append the table name with '-diff' or use an upper case short form
character.

```bash
rimadiff -t xp-diff -t skill-rank-diff
rimadiff -tXR
```

The long and short forms for all the tables can be found on the help
page `rimadiff -h`.
