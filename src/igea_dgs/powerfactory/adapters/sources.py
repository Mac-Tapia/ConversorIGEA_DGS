from .base import EquipmentAdapter


class SourceAdapter(EquipmentAdapter):
    class_name = "ElmXnet"

    def attributes(self, spec):
        return {"bus_external_id": spec.node_id, "uknom": str(spec.nominal_kv)}
