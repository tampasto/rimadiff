from rimadiff.rimadiff_common import RimadiffCommon


class UserSetup(RimadiffCommon):
    ERROR_USERS = 'Missing key users in user-setup table or it is not a list.'
    ERROR_CONFIG = 'Configuration path: {}'
    WARN_ALIAS = (
        'Key user_alias in user-setup table must be a TOML inline table.')

    def __init__(self, setup, history_path):
        users = setup.get('users')
        cls = type(self)
        if not isinstance(users, list):
            self.quit_error(cls.ERROR_USERS, cls.ERROR_CONFIG.format(history_path))
        self.users = [str(u).lower() for u in setup['users']]
        self.user_orig = {str(u).lower(): str(u) for u in setup['users']}

        self.user_alias = {}
        user_alias = setup.get('user_alias')
        if user_alias:
            if not isinstance(user_alias, dict):
                self.warning(cls.WARN_ALIAS)
            else:
                self.user_alias = {
                    str(u).lower(): str(a) for u, a in user_alias.items()}

        self.rima = self.rima_orig = None
        rima = setup.get('rima')
        if rima:
            self.rima = str(rima).lower()
            self.rima_orig = str(rima)
