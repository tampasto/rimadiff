from rimadiff.category import Category
from rimadiff.data_category import DataCategory


# List is filled by ConfigReader.read()
api_categories = []

_skill_cat = Category('skills', 'Skill')
_activity_cat = Category('activities', 'Activity')

label_categories = _skill_cat, _activity_cat

data_categories = (
    DataCategory('skill', 'level', _skill_cat),
    DataCategory('xp', 'xp', _skill_cat),
    DataCategory('skill-rank', 'rank', _skill_cat),
    DataCategory('activity', 'score', _activity_cat),
    DataCategory('activity-rank', 'rank', _activity_cat)
    )
