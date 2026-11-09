import click

from rimadiff.colour_base import ColourBase


class APIResults(ColourBase):
    def __init__(self, data_tuple):
        self.data_tuple = data_tuple

    def echo_success(self, setup):
        success_users = self.data_tuple[0]

        user_map = setup.user_display.get
        if len(success_users):
            click.echo(
                'Downloaded: '
                + ', '.join(map(user_map, success_users)) + '\n'
                )

    def echo_errors(self, setup):
        (
            _,
            fail_users,
            fail_errors,
            bad_json_users,
            wrong_user_data,
        ) = self.data_tuple

        user_map = setup.user_display.get
        if (len(fail_users) or fail_errors.total() or len(bad_json_users)
            or len(wrong_user_data)):
            click.echo()

        if len(fail_users):
            self.error(
                'Could not download: ' + ', '.join(map(user_map, fail_users)))

        if fail_errors.total():
            for text, count in fail_errors.items():
                count_text = f'[{count}x] ' if count > 1 else ''
                self.error(f'{count_text}{text}')
            click.echo()

        if len(bad_json_users):
            self.error(
                'Bad API JSON: ' + ', '.join(map(user_map, bad_json_users)))

        if len(wrong_user_data):
            self.error(
                'API returned data for wrong users, snapshots not saved in '
                'history:'
                )
            for user, user_response in wrong_user_data:
                click.echo(
                    f'  Requested {user_map(user)}, got {user_response}')
            click.echo()
