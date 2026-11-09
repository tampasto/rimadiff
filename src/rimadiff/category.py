class Category:
    def __init__(self, name, display):
        # Attribute id is defined by HistoryManager methods
        # ensure_label_data_category_ids
        # ensure_api_category_ids
        self.id = None
        self.name = name
        self.display = display
