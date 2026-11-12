import re

from rimadiff.categories import label_categories, data_categories
from rimadiff.colour_base import ColourBase


class APIResponse(ColourBase):
    def __init__(self, json_obj, api_id, url=None):
        self.response_user = str(json_obj.get('name')).strip()

        # Special keys for exported files
        json_url = json_obj.get('url')
        self.url = url or json_url
        if not json_url and not url:
            self.url = ''
        self.api_name = json_obj.get('api_name')

        data, labels = self._parse_json_object(json_obj)

        self.data = data
        self.labels = labels
        self.api_id = api_id
        user_id = None

    def _parse_json_object(self, obj):
        # data   [data_category_id]  [label] = value
        # labels [label_category_id] [label] = (display, position)
        failure = None, None

        data = {dc.id: {} for dc in data_categories}
        labels = {lc.id: {} for lc in label_categories}
        clean_re = re.compile(r'[^a-z0-9 ]')
        space_re = re.compile(r'\s+')
        for label_cat in label_categories:
            label_list = obj.get(label_cat.name)
            if not isinstance(label_list, list):
                return failure
            data_cats = [
                dc for dc in data_categories
                if dc.label_category.name == label_cat.name
                ]
            pos_a = f'.{label_cat.name}['
            for entry_i, entry in enumerate(label_list):
                pos_b = pos_a + f'{entry_i}].'
                field_names = ['id', 'name', *(c.name for c in data_cats)]
                field_types = [int, str] + [int] * len(data_cats)
                values = self._get_required_fields(
                    entry, field_names, field_types, pos_b)

                position, label_display, *data_values = values

                label = label_display.strip().lower()
                label = clean_re.sub('', label)
                label = space_re.sub('_', label)

                labels[label_cat.id][label] = label_display, position

                # Miaaouuwww
                for cat_i, data_cat in enumerate(data_cats):
                    data[data_cat.id][label] = data_values[cat_i]

        return data, labels

    def _get_required_fields(self, entry, names, types, pos_b):
        values = []
        for name_i, name in enumerate(names):
            value = entry.get(name)
            type_ = types[name_i]
            if not isinstance(value, type_):
                pos = pos_b + name
                self._quit_type_error(pos, value, type_)
            values.append(value)
        return tuple(values)

    def _quit_type_error(self, pos, value, type_):
        type_dict = {int: 'integer', str: 'string'}
        type_str = type_dict[type_]
        self.quit_error(
            f'API request had an unexpected type at {pos}, '
            f'expected {type_str}, got {value!r}\n'
            f'  Url: {self.url}'
            )
