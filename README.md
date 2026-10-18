# rimadiff
Compare OSRS game hiscores in terminal.

The script can display comparison tables for

* Skill levels
* Skill experiences
* Skill ranks
* Activity scores
* Activity ranks

There is a special username defined as RIMA which will be the focus of
comparison. RIMA is highlighted and it is possible to calculate relative
differences against this user.

The script creates a configuration file in `~/.config/rimadiff.toml` and
stores all downloaded datasets by default in an
[SQLite](https://sqlite.org/) database in `~/.rimadiff_history.db`. It
does not refetch the data for the same day unless forced to do so. See
all command line options with `rimadiff.py -h`.

The default username setup of the configuration file looks like this:

```toml
[user-setup.default]
users = ['Faux', 'Manked', 'Mote Plox', 'Mr Mammal']
user_alias = {'Manked' = 'PKer', 'Mote Plox' = 'Historian'}
rima = 'Faux'
```

This means that username Faux is RIMA. Users Manked and Mote Plox have
aliases PKer and Historian respectively. The alias is shown in the tables
instead of their real usernames. User Mr Mammal will be displayed with
their real username. The configuration file follows
[TOML format](https://toml.io/en/).

You may add multiple user setups by adding more `[user-setup.SETUP_NAME]`
tables.

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

You may also set up the environment using uv.

[Install Astral uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
# If you already have uv, update it (example for .sh script install)
uv self update

cd /path/to/rimadiff
uv sync
```

### Running the tool

```bash
# pip setup
source /path/to/rimadiff/.venv/bin/activate
python3 -m rimadiff

# uv setup
uv run --project /path/to/rimadiff rimadiff
```
