"""
template_library - Editing templates registry and presets store.
"""
from .models import TemplateStore, get_template_store
from .recommender import recommend_template

__all__ = ["TemplateStore", "get_template_store", "recommend_template"]
