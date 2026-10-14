# rimadiff
Compare OSRS game hiscores in terminal.

The script can display comparison tables for

* Skill levels
* Skill experiences
* Activity scores

There is a special username defined as RIMA which will be the focus of
comparison. RIMA is highlighted and it is possible to calculate relative
differences against this user.

The script creates a configuration file in `~/.config/rimadiff.toml` and
stores all downloaded datasets by default in `~/.rimadiff_history`. It
does not refetch the data for the same day unless forced to do so. See
all command line options with `rimadiff.py -h`.

The default operational part of the configuration looks like this:

```toml
users = ['Faux', 'Manked', 'Mote Plox', 'Mr Mammal']
user_alias = {'Manked' = 'PKer', 'Mote Plox' = 'Historian'}
rima = 'Faux'
```

This means that username Faux is RIMA. Users Manked and Mote Plox have
aliases PKer and Historian respectively. This means that the alias is
shown in the tables instead of their real usernames. User Mr Mammal will
be displayed with their real username. The configuration file follows
[TOML format](https://toml.io/en/).
