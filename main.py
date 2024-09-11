import os
import deepl
import fitz
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import  ContentType, LabeledPrice
from aiogram.filters import Command
from wallet import init_db, get_balance, update_balance, send_invoice
from keyboards import get_language_keyboard, get_approval_keyboard, main_menu, get_wallet_keyboard
from dotenv import load_dotenv

load_dotenv()

DEEPL_API_KEY = os.getenv("DEEPL")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
BOT_TOKEN = os.getenv("TG")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

print(DEEPL_API_KEY, PAYMENT_TOKEN, BOT_TOKEN)

class PDFTranslationStates(StatesGroup):
    waiting_for_pdf = State()
    waiting_for_language = State()
    waiting_for_payment = State()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())


@dp.message(F.text == "Отправить файл на перевод")
async def start_translation(message: types.Message, state: FSMContext):
    await message.answer("Пожалуйста, загрузите PDF-документ, который вы хотите перевести.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)

@dp.message(Command("balance"))
async def show_wallet(message: types.Message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    await message.answer(f"Ваш баланс: {balance:.2f} RUB\n\nВыберите сумму для пополнения кошелька", reply_markup=get_wallet_keyboard())

@dp.callback_query(F.data.startswith("top_up_wallet_"))
async def top_up_wallet(callback_query: types.CallbackQuery):
    amount = int(callback_query.data.split("_")[-1])
    await send_invoice(bot, callback_query.message.chat.id, amount)

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message):
    if message.successful_payment.invoice_payload == "wallet_funding_payload":
        user_id = message.from_user.id
        amount = message.successful_payment.total_amount / 100  # Конвертация в рубли
        update_balance(user_id, amount)
        await message.answer(f"Ваш кошелек пополнен на {amount:.2f} RUB.")

@dp.message(PDFTranslationStates.waiting_for_payment, F.text == "Подтвердить")
async def approve_payment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    price_rubles = data.get('price_rubles')

    # Проверяем, достаточно ли средств на балансе
    balance = get_balance(user_id)
    if balance >= price_rubles:
        # Списание средств
        update_balance(user_id, -price_rubles)
        await message.answer(f"Средства в размере {price_rubles:.2f} RUB списаны с вашего кошелька.")

        await message.answer("Выберите язык для перевода:", reply_markup=get_language_keyboard())
        await state.set_state(PDFTranslationStates.waiting_for_language)
    else:
        await message.answer(f"Недостаточно средств на балансе. Ваш баланс: {balance:.2f} RUB.")

@dp.message(PDFTranslationStates.waiting_for_payment, F.text == "Отмена")
async def cancel_payment(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена. Пожалуйста, загрузите новый документ для перевода.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)


@dp.message(PDFTranslationStates.waiting_for_pdf)
async def handle_pdf(message: types.Message, state: FSMContext):
    if message.content_type == ContentType.DOCUMENT:
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        await message.answer("Загружаем ваш файл...")
        doc_file = await bot.download_file(file_path)
        filename = message.document.file_name

        if message.document.mime_type in ('application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'):
            with open(filename, 'wb') as f:
                f.write(doc_file.read())
            await message.answer("Подсчитываем символы...")
            character_count = count_characters_in_pdf(filename)
            price_euros = 20 * (character_count / 1_000_000)
            price_rubles = convert_to_rubles(price_euros)

            await state.update_data(pdf_filename=filename, character_count=character_count, price_rubles=price_rubles)

            user_id = message.from_user.id
            balance = get_balance(user_id)

            if balance >= price_rubles:
                await message.answer(
                    f"Стоимость перевода: {price_rubles:.2f} RUB. Подтвердите списание средств с вашего кошелька.",
                    reply_markup=get_approval_keyboard()
                )
                await state.set_state(PDFTranslationStates.waiting_for_payment)
            else:
                await message.answer(f"Недостаточно средств на балансе. Ваш баланс: {balance:.2f} RUB.", reply_markup=get_wallet_keyboard())
        else:
            await message.answer("Пожалуйста, загрузите PDF или DOCX файл.")


@dp.callback_query(PDFTranslationStates.waiting_for_payment, F.data == "approve_payment")
async def approve_payment(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback_query.from_user.id
    price_rubles = data.get('price_rubles')

    # Списание средств
    update_balance(user_id, -price_rubles)
    await callback_query.message.answer(f"Средства в размере {price_rubles:.2f} RUB списаны с вашего кошелька.")

    await callback_query.message.answer("Выберите язык для перевода:", reply_markup=get_language_keyboard())
    await state.set_state(PDFTranslationStates.waiting_for_language)

@dp.callback_query(PDFTranslationStates.waiting_for_payment, F.data == "cancel_payment")
async def cancel_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer("Операция отменена. Пожалуйста, загрузите новый документ для перевода.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message, state: FSMContext):
    await state.update_data(payment_made=True)
    await message.answer("Оплата прошла успешно! Пожалуйста, выберите язык для перевода:")
    await message.answer("Выберите язык для перевода:", reply_markup=get_language_keyboard())
    await state.set_state(PDFTranslationStates.waiting_for_language)


@dp.callback_query(PDFTranslationStates.waiting_for_language)
async def handle_language_selection(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get('payment_made', False):
        await callback_query.message.answer("Пожалуйста, сначала оплатите перевод.")
        return

    if callback_query.data == 'cancel':
        await state.clear()
        await callback_query.message.answer(
            "Операция отменена. Пожалуйста, загрузите новый PDF-документ, если хотите попробовать снова.")
        await state.set_state(PDFTranslationStates.waiting_for_pdf)
        return

    selected_language = callback_query.data
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

    await callback_query.message.answer("Ваш документ был переведен и отправлен вам.")

    # Reset state to accept a new document
    await state.clear()
    await callback_query.message.answer("Пожалуйста, загрузите новый документ для перевода.")
    await state.set_state(PDFTranslationStates.waiting_for_pdf)


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
    import asyncio
    init_db()
    asyncio.run(dp.start_polling(bot))