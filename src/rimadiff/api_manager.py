import copy
import urllib.parse
from collections import Counter
from numbers import Number

import requests

from rimadiff.api_response import APIResponse
from rimadiff.api_results import APIResults
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
        self._non_numeric_categories = {}
        self._non_int_categories = {}

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

    def download_data(self, user, setup):
        # data   [category] [label_id] = value
        # labels [category] [label_id] = label

        user_original = setup.user_orig[user]
        quoted_user = urllib.parse.quote(user_original, safe='')
        url = self.url.format(quoted_user)

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
            obj = r.json()
            data, labels, user_response = self._response_json_to_data(obj)
            if data is None:
                self._bad_json_users.append(user)
            elif user != user_response.lower():
                self._wrong_user_data.append((user_original, user_response))
            else:
                resp = APIResponse(data, labels, url)

        return resp

    def _response_json_to_data(self, obj):
        # data   [category] [label_id] = value
        # labels [category] [label_id] = label

        user_response = str(obj.get('name')).strip()
        skills = obj.get('skills')
        activities = obj.get('activities')

        not_list = lambda v: not isinstance(v, list)

        if not_list(skills) or not_list(activities):
            return None, None, None

        data = {c.category: {} for c in HistoryManager.CATEGORIES}
        labels = copy.deepcopy(data)

        sk_field_table = {
            'level': 'skill',
            'xp':    'xp',
            'rank':  'skill-rank'
            }
        self._add_json_portion(skills, sk_field_table, data, labels)

        act_field_table = {
            'score': 'activity',
            'rank':  'activity-rank'
            }
        self._add_json_portion(activities, act_field_table, data, labels)

        return data, labels, user_response

    def _add_json_portion(self, obj, field_table, data, labels):
        field_category = {}
        db_cat = HistoryManager.CATEGORIES
        for field, table_name in field_table.items():
            field_category[field] = next(
                c.category for c in db_cat if c.table_name == table_name)

        for entry in obj:
            id_ = entry['id']
            for field in field_table:
                category = field_category[field]

                val = entry[field]
                if not isinstance(val, Number):
                    self._record_numeric_data_type_error(category, field, val)
                elif not isinstance(val, int):
                    self._record_numeric_data_type_error(
                        category, field, val, True)
                data[category][id_] = val

                labels[category][id_] = str(entry['name']).strip()

    def _record_numeric_data_type_error(
        self, category, field, val, for_int=False
    ):
        err_dict = self._non_numeric_categories
        if for_int:
            err_dict = self._non_int_categories
        err_dict.setdefault(category, Counter())
        err_dict[category][val] += 1

    def get_results(self):
        data_tuple = (
            self._success_users,
            self._fail_users,
            self._fail_errors,
            self._bad_json_users,
            self._wrong_user_data,
            self._non_numeric_categories,
            self._non_int_categories
            )
        return APIResults(data_tuple)
