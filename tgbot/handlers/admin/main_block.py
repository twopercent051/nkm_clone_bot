import asyncio
import os
import time

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram import F, Router
from aiogram.utils.markdown import hcode

from create_bot import bot, config
from .filters import AdminFilter
from .inline import AdminInlineKeyboard
from tgbot.misc.states import AdminFSM
from ...services.excel import xlsx_parser
from ...services.orecht import get_card_info
from ...services.ozon_api import OzonAPI

router = Router()
router.message.filter(AdminFilter())

inline = AdminInlineKeyboard()

ozon_api = OzonAPI()

admin_group = config.tg_bot.admin_group


async def main_screen_render(start: bool, user_id: int | str):
    if start:
        text = "Это главный экран бота. Чтобы скопировать карточки товаров, нажмите на клавишу нижу 👇"
    else:
        text = "ГЛАВНОЕ МЕНЮ"
    kb = inline.main_menu_kb()
    await bot.send_message(chat_id=admin_group, text=text, reply_markup=kb)


@router.message(Command("start"))
async def main_block(message: Message, state: FSMContext):
    await state.set_state(AdminFSM.home)
    await main_screen_render(start=True, user_id=message.from_user.id)


@router.callback_query(F.data == "home")
async def main_block(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.home)
    await main_screen_render(start=False, user_id=callback.from_user.id)
    await bot.answer_callback_query(callback.id)


@router.callback_query(F.data == "clone")
async def main_block(callback: CallbackQuery, state: FSMContext):
    text = "Введите ClientID аккаунта"
    kb = inline.home_kb()
    await state.set_state(AdminFSM.client_id)
    await callback.message.answer(text, reply_markup=kb)
    await bot.answer_callback_query(callback.id)


@router.message(F.text, AdminFSM.client_id)
async def main_block(message: Message, state: FSMContext):
    text = "Введите токен"
    kb = inline.home_kb()
    await state.update_data(client_id=message.text.strip())
    await state.set_state(AdminFSM.api_token)
    await message.answer(text, reply_markup=kb)


@router.message(F.text, AdminFSM.api_token)
async def main_block(message: Message, state: FSMContext):
    file_name = f'{os.getcwd()}/template.xlsx'
    file = FSInputFile(path=file_name, filename=file_name)
    text = "Заполните шаблон ссылками и загрузите в бот"
    kb = inline.home_kb()
    await state.update_data(ozon_token=message.text.strip())
    await state.set_state(AdminFSM.get_data)
    await message.answer_document(document=file, caption=text, reply_markup=kb)


@router.message(F.document, AdminFSM.get_data)
async def main_block(message: Message, state: FSMContext):
    file_name = f"{os.getcwd()}/data.xlsx"
    await bot.download(file=message.document, destination=file_name)
    file_data = await xlsx_parser(file=file_name)
    state_data = await state.get_data()
    ozon_token = state_data["ozon_token"]
    client_id = state_data["client_id"]
    if len(file_data) == 0:
        await message.answer("Лист не должен быть пустым")
        return
    await message.answer("Ожидайте... ⏳")
    item_list = []
    for row in file_data:
        if row:
            item = dict(sku=int(row["ozon_id"]), art=row["outer_id"], outer_source=row["outer_source"])
            item_list.append(item)
    task_id = await ozon_api.clone_card(item_list=item_list, ozon_token=ozon_token, client_id=client_id)
    await message.answer(f"ID задачи {hcode(task_id)}\nПроверяем результаты клонирования ⏳")
    await asyncio.sleep(30)
    clone_result = await ozon_api.clone_status(task_id=task_id, ozon_token=ozon_token, client_id=client_id)
    kb = inline.home_kb()
    await asyncio.sleep(1)
    if len(clone_result) > 0:
        text = f"{len(clone_result)} / {len(file_data)} товаров скопированы с ошибками. Запускается " \
               f"парсер\n<u>Внимание! процесс может занять длительное время. Пожалуйста, не прерывайте работу бота</u>"
        await message.answer(text)
    else:
        await message.answer("✅ Все товары скопированы", reply_markup=kb)
        return
    error_items = [dict(offer_id=i["offer_id"], product_id=i["product_id"]) for i in clone_result]
    count_msg = await message.answer(f"Принудительно скопировано 0 / {len(error_items)} товаров")
    counter = 0
    for item in error_items:
        offer_id = item["offer_id"]
        product_id = item["product_id"]
        try:
            card_attrs = await ozon_api.get_card_attrs(offer_id=offer_id, ozon_token=ozon_token, client_id=client_id)
            time.sleep(9)
            await ozon_api.delete_cards(ozon_token=ozon_token,
                                        client_id=client_id,
                                        archive_item=[product_id],
                                        delete_item=[{"offer_id": offer_id}])
            if offer_id.split("-")[0] == "РСВ":
                oreht_data = await get_card_info(item_art=offer_id.split("-")[-1])
                if not oreht_data:
                    await message.answer("Неправильная ссылка в Oreht")
                    continue
                images = [oreht_data["image"]]
            else:
                images = [i["file_name"] for i in card_attrs["result"][0]["images"]]
            result = await ozon_api.create_card(income_data=card_attrs,
                                                images=images,
                                                price=str(2000),
                                                ozon_token=ozon_token,
                                                client_id=client_id)
            if result:
                counter += 1
                await count_msg.edit_text(f"Принудительно скопировано {counter} / {len(error_items)} товаров")
            else:
                await message.answer(f"{offer_id} не найден")
        except Exception as ex:
            await message.answer(f"{offer_id} error: {ex}")

    os.remove(file_name)
    await state.set_state(AdminFSM.home)
    text = "✅ Цикл завершён"
    await message.answer(text, reply_markup=kb)
