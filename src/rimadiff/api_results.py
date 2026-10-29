import click

from rimadiff.rimadiff_common import RimadiffCommon


class APIResults(RimadiffCommon):
    def __init__(self, data_tuple):
        self.data_tuple = data_tuple

    def echo(self, setup):
        (
            success_users,
            fail_users,
            fail_errors,
            bad_json_users,
            wrong_user_data,
            non_numeric_categories,
            non_int_categories
        ) = self.data_tuple

        user_map = setup.user_orig.get
        if len(success_users):
            click.echo(
                'Downloaded: '
                + ', '.join(map(user_map, success_users)) + '\n'
                )

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

        numeric_errs = (
            (non_numeric_categories, 'numeric'),
            (non_int_categories, 'integer')
            )
        for num_dict, label in numeric_errs:
            if len(num_dict) == 0:
                continue
            self.warning(f'The API returned non-{label} datapoints for:')
            cat_header = {c.category: c.header for c in HistoryManager.CATEGORIES}
            for category, value_counter in num_dict.items():
                vals = ', '.join(
                    repr(val) + ('' if count == 1 else f' (x{count})')
                    for val, count in value_counter.items()
                    )
                click.echo(f'  {cat_header[category]}: {vals}')
