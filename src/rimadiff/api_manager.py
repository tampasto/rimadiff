from collections import Counter
from numbers import Number

import requests

from rimadiff.api_response import APIResponse
from rimadiff.api_results import APIResults
from rimadiff.categories import api_categories
from rimadiff.history_manager import HistoryManager


class APIManager:
    def __init__(self, url):
        self.url = url

        self._session = None

        self._success_users = []
        self._fail_users = []
        self._fail_errors = Counter()
        self._bad_json_users = []
        self._wrong_user_data = []

    def __enter__(self):
        self.open()
        return self

    def open(self):
        self._session = requests.Session()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self):
        self._session.close()

    def download_data(self, user, setup, api_name):
        # data   [data_category_id]  [label] = value
        # labels [label_category_id] [label] = (display, position)

        user_display = setup.user_display[user]
        url = self.url[api_name].format(user_display)

        api_cat = next(c for c in api_categories if c.name == api_name)
        api_id = api_cat.id

        resp = None
        try:
            r = self._session.get(url)
            r.raise_for_status()
        except requests.RequestException as err:
            self._fail_users.append(user)
            err_str = f'{type(err).__name__}: {err}'
            self._fail_errors[err_str] += 1
        else:
            self._success_users.append(user)
            json_obj = r.json()
            resp = APIResponse(json_obj, api_id, url)
            if resp.data is None:
                self._bad_json_users.append(user)
                resp = None
            elif user != resp.response_user.lower():
                self._wrong_user_data.append((user_display, response_user))
                resp = None
        return resp

    def get_results(self):
        data_tuple = (
            self._success_users,
            self._fail_users,
            self._fail_errors,
            self._bad_json_users,
            self._wrong_user_data,
            )
        return APIResults(data_tuple)
