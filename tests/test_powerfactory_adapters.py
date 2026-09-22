from decimal import Decimal

import pytest

from igea_dgs.domain.equipment import SolarPlantSpec, ThermalGeneratorSpec
from igea_dgs.powerfactory import AdapterApplyError, SolarAdapter, ThermalAdapter

from fakes.fake_powerfactory import FakePowerFactory


def test_solar_adapter_is_idempotent():
    fake = FakePowerFactory()
    spec = SolarPlantSpec("PV-1", "N1", Decimal("13.2"), Decimal("5"), Decimal("0.98"))
    adapter = SolarAdapter(fake)

    adapter.apply(spec)
    adapter.apply(spec)

    assert fake.count("ElmGenstat", "PV-1") == 1


def test_adapter_rolls_back_created_objects_on_failure():
    fake = FakePowerFactory()
    spec = ThermalGeneratorSpec(
        "GT-1", "N1", Decimal("13.2"), Decimal("10"), Decimal("12"), "FAIL"
    )

    with pytest.raises(AdapterApplyError):
        ThermalAdapter(fake).apply(spec)

    assert fake.objects_created_in_current_unit == []
    assert fake.objects == []
