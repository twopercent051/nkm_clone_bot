import asyncio
import itertools
import json
from typing import List

import aiohttp

from create_bot import config, logger


# ozon_token = config.misc.ozon_token
# ozon_client_id = config.misc.ozon_client_id


class OzonAPI:

    def __init__(self):
        pass

    @staticmethod
    async def __paginator(item_list: list, size: int) -> List[tuple]:
        it = iter(item_list)
        return iter(lambda: tuple(itertools.islice(it, size)), ())

    @staticmethod
    async def __request(url: str, data: dict, ozon_token: str, client_id: int):
        headers = {
            'Content-Type': 'application/json',
            "Host": "api-seller.ozon.ru",
            "Api-Key": ozon_token,
            "Client-Id": client_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url=url, headers=headers, data=data) as resp:
                return await resp.json()

    async def clone_card(self, item_list: list, ozon_token: str, client_id: int) -> list:
        url = "https://api-seller.ozon.ru/v1/product/import-by-sku"
        items = []
        for item in item_list:
            if item["outer_source"] == "orecht":
                offer_id = f"РСВ-{item['art']}РСВ-{item['art']}"
            else:
                offer_id = f"УНАС-{item['art']}"
            item_dict = dict(sku=item["sku"],
                             offer_id=offer_id,
                             currency_code="RUB",
                             old_price=str(2000),
                             price=str(2000),
                             vat="0")
            items.append(item_dict)
        data = dict(items=items)
        data = json.dumps(data)
        task = await self.__request(url=url, data=data, ozon_token=ozon_token, client_id=client_id)
        return task["result"]["task_id"]

    async def clone_status(self, task_id: int, ozon_token: str, client_id: int) -> dict:
        url = "https://api-seller.ozon.ru/v1/product/import/info"
        data = dict(task_id=task_id)
        data = json.dumps(data)
        result = await self.__request(url=url, data=data, ozon_token=ozon_token, client_id=client_id)
        items_result = result["result"]["items"]
        for item in items_result:
            logger.warning(item)
        errors = []
        for item in items_result:
            if len(item["errors"]) > 0 and item["product_id"] != 0:
                errors.append(dict(offer_id=item["offer_id"],
                                   product_id=item["product_id"],
                                   error=item["errors"][0]["code"]))
        return errors

    async def delete_cards(self, archive_item_list: list, delete_item_list: list, ozon_token: str, client_id: int):
        delete_url = "https://api-seller.ozon.ru/v2/products/delete"
        archive_url = "https://api-seller.ozon.ru/v1/product/archive"
        archive_item_chunks = await self.__paginator(item_list=archive_item_list, size=100)
        delete_item_chunks = await self.__paginator(item_list=delete_item_list, size=300)
        for chunk in archive_item_chunks:
            data = dict(product_id=list(chunk))
            data = json.dumps(data)
            a = await self.__request(url=archive_url, data=data, ozon_token=ozon_token, client_id=client_id)
        await asyncio.sleep(1)
        for chunk in delete_item_chunks:
            data = dict(products=list(chunk))
            data = json.dumps(data, ensure_ascii=False)
            b = await self.__request(url=delete_url, data=data, ozon_token=ozon_token, client_id=client_id)
            await asyncio.sleep(1)

    async def get_card_attrs(self, offer_id: str, ozon_token: str, client_id: int) -> dict:
        url = "https://api-seller.ozon.ru/v3/products/info/attributes"
        data = dict(filter=dict(offer_id=[offer_id], visibility="ALL"), limit=100)
        data = json.dumps(data)
        result = await self.__request(url=url, data=data, ozon_token=ozon_token, client_id=client_id)
        return result

    async def create_card(self, income_data: dict, images: List[str], price: int, ozon_token: str, client_id: int):
        url = "https://api-seller.ozon.ru/v2/product/import"
        try:
            item_data = income_data["result"][0]
        except KeyError:
            return None
        attrs = []
        for attr in item_data["attributes"]:
            if attr["attribute_id"] == 9024:
                id_attr = dict(id=9084,
                               complex_id=0,
                               values=[dict(dictionary_value_id=0, value=item_data["offer_id"])])
            else:
                id_attr = dict(id=attr["attribute_id"],
                               complex_id=attr["complex_id"],
                               values=attr["values"])
            attrs.append(id_attr)
        data = dict(items=[dict(attributes=attrs,
                                category_id=item_data["category_id"],
                                currency_code="RUB",
                                depth=item_data["depth"],
                                dimension_unit=item_data["dimension_unit"],
                                height=item_data["height"],
                                images=images,
                                name=item_data["name"],
                                offer_id=item_data["offer_id"],
                                old_price=str(price),
                                price=str(price),
                                vat="0",
                                weight=item_data["weight"],
                                weight_unit=item_data["weight_unit"],
                                width=item_data["width"])])
        data = json.dumps(data)
        return await self.__request(url=url, data=data, ozon_token=ozon_token, client_id=client_id)


async def test():
    ozon = OzonAPI()
    token = "99fd2635-b49e-43ea-9bb6-a7bbdf7a0100"
    client_id = "667260"
    await ozon.clone_status(task_id=863516561, ozon_token=token, client_id=client_id)


if __name__ == "__main__":
    asyncio.run(test())
