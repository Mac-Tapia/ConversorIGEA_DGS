from .base import EquipmentAdapter


class ThermalAdapter(EquipmentAdapter):
    class_name = "ElmSym"

    def attributes(self, spec):
        return {
            "bus_external_id": spec.node_id,
            "uknom": str(spec.nominal_kv),
            "pgini": str(spec.rated_mw),
            "sgn": str(spec.rated_mva),
            "technology": spec.technology,
        }
