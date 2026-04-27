import pytest

from app.infrastructure.services.ai_manager import tools
from app.infrastructure.services.ai_manager.tools import AIManagerTools


@pytest.mark.asyncio
async def test_ai_manager_subscription_tool_rejects_assisted_subscription_type():
    result = await AIManagerTools().add_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        subscription_type="assisted_selection_requests",
    )

    assert result.ok is False
    assert result.message == "Неизвестный тип подписки."


@pytest.mark.asyncio
async def test_lookup_lot_by_number_returns_card_from_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "salesdata.csv"
    csv_path.write_text(
        "Lot number,Id,Year,Make,Model Detail,Model Group,Body Style,Color,"
        "Odometer,Engine,Drive,Transmission,Sale Date M/D/CY,Buy-It-Now Price,"
        '"High Bid =non-vix,Sealed=Vix",Est. Retail Value,Image Thumbnail,Image URL,Fuel Type\n'
        "12345678,1,2021,Toyota,Camry,Camry,Sedan,WHITE,50000,2.5,FWD,AUTOMATIC,"
        "20260501,15000,12000,22000,https://example.com/car.jpg,,GAS\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "_CSV_PATH", str(csv_path))

    result = await AIManagerTools().lookup_lot_by_number("https://www.copart.com/lot/12345678")

    assert result.ok is True
    assert result.payload is not None
    car = result.payload["car"]
    assert car.lot_number == "12345678"
    assert car.make == "Toyota"
    assert car.model == "Camry"
    assert result.payload["lot"]["fuel_type"] == "GAS"
    assert result.payload["lot"]["price_usd"] == 15000.0


@pytest.mark.asyncio
async def test_create_lead_retries_once_after_transient_failure(monkeypatch):
    calls = []

    async def fake_bitrix_send_data(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return '{"result": 1}'

    monkeypatch.setattr(tools, "bitrix_send_data", fake_bitrix_send_data)

    result = await AIManagerTools().create_lead(
        tg_login="user",
        tg_id=123,
        data={"name": "Иван"},
        method="ai_manager_chat",
    )

    assert result.ok is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_quick_vehicle_specs_uses_csv_characteristics(tmp_path, monkeypatch):
    csv_path = tmp_path / "salesdata.csv"
    csv_path.write_text(
        "Lot number,Id,Year,Make,Model Detail,Model Group,Body Style,Color,"
        "Odometer,Engine,Drive,Transmission,Sale Date M/D/CY,Buy-It-Now Price,"
        '"High Bid =non-vix,Sealed=Vix",Est. Retail Value,Image Thumbnail,Image URL,Fuel Type\n'
        "11111111,1,2023,Tesla,Model Y,Model Y,SUV,WHITE,12000,,AWD,AUTOMATIC,"
        "20260501,25000,21000,35000,https://example.com/tesla.jpg,,ELECTRIC\n"
        "22222222,2,2021,Toyota,Camry,Camry,Sedan,BLACK,30000,2.5,FWD,AUTOMATIC,"
        "20260502,18000,15000,26000,https://example.com/camry.jpg,,GAS\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "_CSV_PATH", str(csv_path))

    result = await AIManagerTools().quick_vehicle_specs(
        brand="Tesla",
        model="Model Y",
        year_from=2022,
        year_to=2024,
    )

    assert result.ok is True
    specs = result.payload["specs"]
    assert specs["fuel_types"] == ["ELECTRIC"]
    assert specs["is_electric"] is True
    assert "0%" in result.message


@pytest.mark.asyncio
async def test_estimate_landed_cost_for_ev_lot_uses_known_csv_price_and_zero_customs(
    tmp_path,
    monkeypatch,
):
    csv_path = tmp_path / "salesdata.csv"
    csv_path.write_text(
        "Lot number,Id,Year,Make,Model Detail,Model Group,Body Style,Color,"
        "Odometer,Engine,Drive,Transmission,Sale Date M/D/CY,Buy-It-Now Price,"
        '"High Bid =non-vix,Sealed=Vix",Est. Retail Value,Image Thumbnail,Image URL,Fuel Type\n'
        "90141575,1,2025,CHEVROLET,EQUINOX,EQUINOX,SPORT UTILITY VEHICLE,RED,"
        "6072,,FWD,AUTOMATIC,20260428,7899,6200,30000,https://example.com/equinox.jpg,,ELECTRIC\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "_CSV_PATH", str(csv_path))

    result = await AIManagerTools().estimate_landed_cost_for_lot(
        lot_query="90141575",
        shipping_mode="container",
    )

    assert result.ok is True
    estimate = result.payload["estimate"]
    assert estimate["lot_price_usd"] == 7899.0
    assert estimate["customs_usd"] == 0.0
    assert estimate["catalog_benchmark"]["lo_usd"] == 20_000
    assert estimate["catalog_benchmark"]["hi_usd"] == 30_000
    assert estimate["indicative_total_range_usd"] == (20_000, 30_000)
    assert estimate["known_subtotal_usd"] == 7899.0
    assert "Пошлина/НДС для EV: $0" in result.message
    assert "ориентир по cars.md: $20 000-$30 000" in result.message
    assert "ремонт" in result.message.lower()


@pytest.mark.asyncio
async def test_estimate_landed_cost_can_use_brand_model_year_without_lot():
    result = await AIManagerTools().estimate_landed_cost_for_lot(
        lot_query="",
        brand="Chevrolet",
        model="Equinox",
        year=2025,
        fuel_type="ELECTRIC",
    )

    assert result.ok is True
    estimate = result.payload["estimate"]
    assert estimate["catalog_benchmark"]["model"] == "Chevrolet Equinox EV"
    assert estimate["indicative_total_range_usd"] == (20_000, 30_000)
    assert "марка/модель/год" in result.message.lower()
    assert "менеджер" in result.message.lower()
