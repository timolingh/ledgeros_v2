from apps.accounting.models import Entity


def get_default_entity() -> Entity:
    return Entity.get_default()
