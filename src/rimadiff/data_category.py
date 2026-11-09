from rimadiff.category import Category


class DataCategory(Category):
    def __init__(self, table_name, name, label_category, display=None):
        super().__init__(name, display)
        if not self.display:
            self.display = name

        self.table_name = table_name
        self.label_category = label_category

    @property
    def header(self):
        return self.label_category.display + ' ' + self.display
