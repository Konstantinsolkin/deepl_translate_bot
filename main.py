import fitz
import deepl
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ContentType
from aiogram.filters import Command
from wallet import init_db, get_balance, update_balance, send_invoice
from keyboards import get_language_keyboard, get_approval_keyboard, main_menu, get_wallet_keyboard
from dotenv import load_dotenv
from docx import Document

logging.basicConfig(level=logging.INFO)

load_dotenv()

BOT_TOKEN = os.getenv("TG")
DEEPL_API_KEY = os.getenv("DEEP")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class PDFTranslationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_payment = State()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer("Добро пожаловать! Отправьте PDF файл для перевода или выберите другое действие:",
                         reply_markup=main_menu())


@dp.message(F.text == "Отправить файл на перевод")
async def prompt_for_file(message: types.Message):
    await message.answer("Пожалуйста, отправьте PDF файл для перевода.")


@dp.message(F.content_type == ContentType.DOCUMENT)
async def handle_pdf(message: types.Message, state: FSMContext):
    if message.document.mime_type == 'application/pdf':
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        await message.answer("Загружаем ваш файл...")
        doc_file = await bot.download_file(file_path)
        filename = message.document.file_name

        with open(filename, 'wb') as f:
            f.write(doc_file.read())

        await message.answer("Подсчитываем символы...")
        character_count = count_characters_in_pdf(filename)
        price_euros = 20 * (character_count / 1_000_000)
        price_rubles = convert_to_rubles(price_euros)

        await state.update_data(pdf_filename=filename, character_count=character_count, price_rubles=price_rubles)

        await message.answer(f"Количество знаков в документе: {character_count}\n"
                             f"Стоимость перевода: {price_rubles:.2f} RUB")

        await message.answer("Выберите язык для перевода:", reply_markup=get_language_keyboard())
        await state.set_state(PDFTranslationStates.waiting_for_language)
    else:
        await message.answer("Пожалуйста, отправьте PDF файл.")


@dp.callback_query(PDFTranslationStates.waiting_for_language)
async def handle_language_selection(callback_query: types.CallbackQuery, state: FSMContext):
    selected_language = callback_query.data
    await state.update_data(selected_language=selected_language)

    data = await state.get_data()
    price_rubles = data.get('price_rubles')
    user_id = callback_query.from_user.id
    balance = get_balance(user_id)

    if balance >= price_rubles:
        await callback_query.message.answer(
            f"Подтвердите списание средств с вашего кошелька в размере {price_rubles:.2f} RUB.",
            reply_markup=get_approval_keyboard()
        )
        await state.set_state(PDFTranslationStates.waiting_for_payment)
    else:
        await callback_query.message.answer(f"Недостаточно средств на балансе. Ваш баланс: {balance:.2f} RUB.",
                                            reply_markup=get_wallet_keyboard())


@dp.callback_query(PDFTranslationStates.waiting_for_payment, F.data == "approve_payment")
async def approve_payment(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback_query.from_user.id
    price_rubles = data.get('price_rubles')
    pdf_filename = data.get('pdf_filename')
    selected_language = data.get('selected_language')

    if not pdf_filename or not os.path.exists(pdf_filename):
        await callback_query.message.answer("Не удалось найти PDF-файл. Пожалуйста, загрузите документ снова.")
        await state.clear()
        return

    update_balance(user_id, -price_rubles)
    await callback_query.message.answer(f"Средства в размере {price_rubles:.2f} RUB списаны с вашего кошелька.")

    await callback_query.message.answer(f"Переводим ваш документ на {selected_language}...")

    translator = deepl.Translator(DEEPL_API_KEY)
    translated_filename = f"translated_{os.path.splitext(os.path.basename(pdf_filename))[0]}.docx"

    try:
        doc = fitz.open(pdf_filename)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        translated_text = translator.translate_text(text, target_lang=selected_language).text

        document = Document()
        document.add_paragraph(translated_text)
        document.save(translated_filename)

        await bot.send_document(callback_query.message.chat.id, types.FSInputFile(translated_filename))
        await callback_query.message.answer("Ваш документ был переведен и отправлен вам в формате DOCX.")

    except deepl.DeepLException as deepl_error:
        await callback_query.message.answer(f"Ошибка во время перевода: {deepl_error}")
    except Exception as general_error:
        await callback_query.message.answer(f"Неожиданная ошибка: {general_error}")
    finally:
        try:
            os.remove(pdf_filename)
            os.remove(translated_filename)
        except Exception as cleanup_error:
            await callback_query.message.answer(f"Ошибка при удалении временных файлов: {cleanup_error}")

    await state.clear()
    await callback_query.message.answer("Пожалуйста, отправьте новый PDF-документ для перевода.")


@dp.callback_query(PDFTranslationStates.waiting_for_payment, F.data == "cancel_payment")
async def cancel_payment(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.answer("Операция отменена. Пожалуйста, отправьте новый PDF-документ для перевода.")


@dp.message(Command("balance"))
async def show_wallet(message: types.Message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    await message.answer(f"Ваш баланс: {balance:.2f} RUB\n\nВыберите сумму для пополнения кошелька:", reply_markup=get_wallet_keyboard())

@dp.callback_query(F.data.startswith("top_up_wallet_"))
async def top_up_wallet(callback_query: types.CallbackQuery):
    logging.info(f"Получен callback запрос: {callback_query.data}")
    amount = int(callback_query.data.split("_")[-1])
    try:
        await send_invoice(bot, callback_query.from_user.id, amount, PAYMENT_TOKEN)
        await callback_query.answer("Выставлен счет на оплату. Пожалуйста, проверьте и подтвердите платеж.")
        logging.info(f"Счет на {amount} RUB выставлен пользователю {callback_query.from_user.id}")
    except Exception as e:
        logging.error(f"Ошибка при выставлении счета: {e}")
        await callback_query.answer("Произошла ошибка при выставлении счета. Пожалуйста, попробуйте позже.")

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    logging.info(f"Получен pre-checkout запрос: {pre_checkout_query.id}")
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: types.Message):
    logging.info(f"Получено уведомление об успешном платеже: {message.successful_payment}")
    if message.successful_payment.invoice_payload == "wallet_funding_payload":
        user_id = message.from_user.id
        amount = message.successful_payment.total_amount / 100
        update_balance(user_id, amount)
        await message.answer(f"Ваш кошелек пополнен на {amount:.2f} RUB.")
        logging.info(f"Баланс пользователя {user_id} пополнен на {amount} RUB")

@dp.callback_query()
async def process_callback_query(callback_query: types.CallbackQuery):
    logging.info(f"Получен необработанный callback запрос: {callback_query.data}")
    await callback_query.answer("Обработка запроса...")


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
    logging.info("Бот запущен")
    asyncio.run(dp.start_polling(bot))