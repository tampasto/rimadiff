from dataclasses import dataclass


@dataclass
class Category:
    table_name: str
    category: int
    header: str
