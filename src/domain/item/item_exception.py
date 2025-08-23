class ItemException(Exception):
    pass


class ItemNotFoundException(ItemException):
    pass


class ItemNotUsableException(ItemException):
    pass


class ItemNotEquippableException(ItemException):
    pass