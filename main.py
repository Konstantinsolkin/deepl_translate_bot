import deepl
import fitz
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.filters import Command
import aiohttp
import os

DEEPL_API_KEY = ""
bot = Bot(token="")
dp = Dispatcher(storage=MemoryStorage())

class PDFTranslationStates(StatesGroup):
    waiting_for_pdf = State()
    waiting_for_language = State()

def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 English", callback_data="EN"),
         InlineKeyboardButton(text="🇪🇸 Spanish", callback_data="ES")],
        [InlineKeyboardButton(text="🇫🇷 French", callback_data="FR"),
         InlineKeyboardButton(text="🇩🇪 German", callback_data="DE")],
        [InlineKeyboardButton(text="🇮🇹 Italian", callback_data="IT"),
         InlineKeyboardButton(text="🇵🇹 Portuguese", callback_data="PT")],
        [InlineKeyboardButton(text="🇳🇱 Dutch", callback_data="NL"),
         InlineKeyboardButton(text="🇯🇵 Japanese", callback_data="JA")],
        [InlineKeyboardButton(text="🇷🇺 Russian", callback_data="RU"),
         InlineKeyboardButton(text="🇨🇳 Chinese", callback_data="ZH")],
        [InlineKeyboardButton(text="🇹🇷 Turkish", callback_data="TR")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    return keyboard

@dp.message(Command("start"))
async def start_translation(message: types.Message, state: FSMContext):
    await message.answer("Пожалуйста, загрузите PDF-документ, который вы хотите перевести.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)

@dp.message(PDFTranslationStates.waiting_for_pdf)
async def handle_pdf(message: types.Message, state: FSMContext):
    if message.content_type == ContentType.DOCUMENT and message.document.mime_type == 'application/pdf':
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        await message.answer("Загружаем ваш файл...")
        pdf_file = await bot.download_file(file_path)
        pdf_filename = message.document.file_name
        with open(pdf_filename, 'wb') as f:
            f.write(pdf_file.read())
        await message.answer("Подсчитываем количество символов...")
        character_count = count_characters_in_pdf(pdf_filename)
        price_euros = 20 * (character_count / 1_000_000)
        price_rubles = convert_to_rubles(price_euros)
        await message.answer(f"Оценочная стоимость: {price_euros:.3f} EUR ({price_rubles:.2f} RUB). Пожалуйста, выберите язык для перевода:")
        await state.update_data(pdf_filename=pdf_filename)
        await state.set_state(PDFTranslationStates.waiting_for_language)
        await message.answer("Выберите язык для перевода:", reply_markup=get_language_keyboard())
    else:
        await message.answer("Пожалуйста, загрузите корректный PDF-файл.")

@dp.callback_query(PDFTranslationStates.waiting_for_language)
async def handle_language_selection(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == 'cancel':
        await state.clear()
        await callback_query.message.answer("Операция отменена. Пожалуйста, загрузите новый PDF-документ, если хотите попробовать снова.")
        await state.set_state(PDFTranslationStates.waiting_for_pdf)
        return

    selected_language = callback_query.data
    data = await state.get_data()
    pdf_filename = data.get("pdf_filename")

    if not pdf_filename or not os.path.exists(pdf_filename):
        await callback_query.message.answer("Не удалось найти PDF-файл. Пожалуйста, загрузите документ снова.")
        await state.set_state(PDFTranslationStates.waiting_for_pdf)
        return

    await callback_query.message.answer(f"Переводим ваш документ на {selected_language}...")

    translator = deepl.Translator(DEEPL_API_KEY)
    translated_filename = f"translated_{os.path.basename(pdf_filename)}"

    try:
        with open(pdf_filename, "rb") as pdf_file, open(translated_filename, "wb") as translated_file:
            translator.translate_document(
                input_document=pdf_file,
                output_document=translated_file,
                target_lang=selected_language
            )

    except deepl.DeepLException as deepl_error:
        await callback_query.message.answer(f"Ошибка во время перевода: {deepl_error}")
        return
    except Exception as general_error:
        await callback_query.message.answer(f"Неожиданная ошибка: {general_error}")
        return

    if os.path.exists(translated_filename):
        try:
            await bot.send_document(callback_query.message.chat.id, types.FSInputFile(translated_filename))
        except Exception as send_error:
            await callback_query.message.answer(f"Ошибка при отправке переведенного документа: {send_error}")
    else:
        await callback_query.message.answer("Перевод не удался. Переведенный файл не был создан.")

    try:
        os.remove(pdf_filename)
        os.remove(translated_filename)
    except Exception as cleanup_error:
        await callback_query.message.answer(f"Ошибка при удалении временных файлов: {cleanup_error}")

    await state.clear()
    await callback_query.message.answer("Ваш документ был переведен и отправлен вам.")

@dp.callback_query(F.data == 'cancel')
async def handle_cancel(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer("Операция была отменена. Пожалуйста, загрузите новый PDF-документ, если хотите попробовать снова.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)

def count_characters_in_pdf(file_path: str) -> int:
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return len(text)

def convert_to_rubles(price_euros):
    conversion_rate = 100
    return price_euros * conversion_rate

if __name__ == '__main__':
    dp.run_polling(bot)
