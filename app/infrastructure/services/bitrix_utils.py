import aiohttp


# Функция формирования url для битрикса
async def make_bitrix_url(tg_login: str, tg_id: int, data: dict, method: str) -> str:
    if method == "consultation_request":
        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]=Консультация (TgBot)&"
            f"FIELDS[NAME]={data.get('name')}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
        )

    elif method == "self_selection":
        lot_description = data.get("lot").split("-")
        lot_number = lot_description[0][7:]
        brand = lot_description[1]
        model = lot_description[2]
        url = (
            f"https://intertrade.bitrix24.by/rest/61/jfx53ycydgyyr39c/crm.lead.add.json?"
            f"FIELDS[TITLE]={brand} {model} (TgBot)&"
            f"FIELDS[NAME]={data.get('name')}&"
            f"FIELDS[PHONE][0][VALUE]={data.get('phone')}&"
            f"FIELDS[PHONE][0][VALUE_TYPE]=Мобильный&"
            f"FIELDS[IM][0][VALUE]=@{tg_login if tg_login else tg_id}&"
            f"FIELDS[IM][0][VALUE_TYPE]=Telegram&"
            f"FIELDS[COMMENTS]=Лот №: {lot_number} | "
            f"https://www.copart.com/lot/{lot_number}/"
        )

    return url


# Функция отправки лидов в битрикс
async def bitrix_send_data(tg_login: str, tg_id: int, data: dict, method: str) -> None:
    url = await make_bitrix_url(tg_login, tg_id, data, method)
    async with aiohttp.ClientSession() as session:
        async with session.post(url) as resp:
            response = await resp.text()
            return response
