from .base import EquipmentAdapter


class SolarAdapter(EquipmentAdapter):
    class_name = "ElmGenstat"

    def attributes(self, spec):
        return {
            "bus_external_id": spec.node_id,
            "uknom": str(spec.nominal_kv),
            "pgini": str(spec.rated_mw),
            "cosn": str(spec.power_factor),
            "technology": "solar",
        }
