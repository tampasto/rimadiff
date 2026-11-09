from rimadiff.colour_base import ColourBase


class UserSetup(ColourBase):
    ERROR_USERS = 'Missing key users in user-setup table or it is not a list.'
    ERROR_CONFIG = 'Configuration path: {}'
    WARN_ITABLE = 'Key {} in user-setup table must be a TOML inline table.'
    ERROR_API_NAMES = (
        'User setup {} defines unrecognized API names in default_api and/or '
        'user_api keys.\n  Defined: {}\n  Expected: {}'
        )

    def __init__(self, setup, general_config_path):
        lower = lambda t: str(t).strip().lower()
        strip = lambda t: str(t).strip()

        # Key 'users'
        users = setup.get('users')
        if not isinstance(users, list):
            self.quit_error(
                UserSetup.ERROR_USERS,
                UserSetup.ERROR_CONFIG.format(general_config_path)
                )
        self.users = [lower(u) for u in setup['users']]
        self.user_display = {lower(u): strip(u) for u in setup['users']}

        # Key 'rima'
        self.rima = self.rima_display = None
        rima = setup.get('rima')
        if rima:
            self.rima = lower(rima)
            self.rima_display = strip(rima)

        # Key 'user_alias'
        self.user_alias = {}
        user_alias = self._get_inline_table(setup, 'user_alias')
        if user_alias:
            self.user_alias = {lower(u): str(a) for u, a in user_alias.items()}

        # Key 'default_api'
        self.default_api = setup.get('default_api') or 'main'

        # Key 'user_api'
        self.user_api = {}
        user_api = self._get_inline_table(setup, 'user_api')
        if user_api:
            self.user_api = {lower(u): strip(a) for u, a in user_api.items()}

        self._api_names = None

    @property
    def api_names(self):
        if self._api_names is None:
            api_names = set()
            for user in self.users:
                name = self.get_user_api_name(user)
                api_names.add(name)
            self._api_names = sorted(api_names)
        return self._api_names

    def validate_api_names(self, setup_name, correct_names):
        bad_names = {n for n in self.api_names if n not in correct_names}
        if bad_names:
            defined = ', '.join(sorted(bad_names))
            expected = ', '.join(correct_names)
            msg = UserSetup.ERROR_API_NAMES.format(
                setup_name, defined, expected)
            self.quit_error(msg)

    def get_user_api_name(self, user):
        if user in self.user_api:
            return self.user_api[user]
        else:
            return self.default_api

    def _get_inline_table(self, setup, key):
        table = setup.get(key)
        if table:
            if not isinstance(table, dict):
                self.warning(UserSetup.WARN_ITABLE.format(key))
        return table
