from .base import EquipmentAdapter


class GenericEquipmentAdapter(EquipmentAdapter):
    def __init__(self, port, class_name):
        super().__init__(port)
        self.class_name = class_name

    def attributes(self, spec):
        return dict(spec)
