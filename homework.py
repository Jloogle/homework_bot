import json
import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='bot.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('logger.log',
                              maxBytes=50000000,
                              backupCount=5)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)


def send_message(bot, message):
    """Функция отправки сообщения ботом в чат TELEGRAM_CHAT_ID."""
    LOG_MESSAGE = f'Бот отправил сообщение: {message}'
    ERROR_MESSAGE_TELEGRAM = ('Не удалось отправить сообщение пользователю!,'
                              ' ошибка {error}')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=message)
        logger.info(LOG_MESSAGE)
    except telegram.TelegramError as error:
        logger.error(ERROR_MESSAGE_TELEGRAM.format(error=error))
        raise error


def get_api_answer(current_timestamp):
    """Получает ответ от API-сервиса и преобразует его в тип данных Python."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    ERROR_MESSAGE_REQ = (f'API не отвечает, при обращении к {ENDPOINT} '
                         'код ошибки: {error}'
                         )
    MESSAGE = ('Код ответа не соответствует ожидаемому '
               f'при запросе к {ENDPOINT}')
    ERROR_MESSAGE_JSON = 'Не удалось получить данные в формате JSON'
    try:
        homework_status = requests.get(ENDPOINT, headers=HEADERS,
                                       params=params)
    except requests.RequestException as error:
        logger.error(ERROR_MESSAGE_REQ.format(error=error))
        raise error
    if homework_status.status_code != HTTPStatus.OK:
        logger.error(MESSAGE)
        raise ValueError(MESSAGE)
    try:
        return homework_status.json()
    except json.decoder.JSONDecodeError as error:
        logger.error(ERROR_MESSAGE_JSON)
        raise error


def check_response(response):
    """
    Функция проверки на корректный ответ от API.
    Возвращает список домашних работ.
    """
    ERROR_MESSAGE_KEY = 'Искомых ключей в ответе запроса API не найдено'
    ERROR_MESSAGE_ISIN = ('Под ключом "homeworks" в ответ приходит'
                          ' недопустимый тип данных')
    MESSEGE_DEBUG = ('Статус ваших домашних работ со времени'
                     ' {current_date} не изменился.')
    try:
        homeworks = response['homeworks']
        current_date = response['current_date']
    except KeyError as error:
        logger.error(ERROR_MESSAGE_KEY)
        raise error
    else:
        if not isinstance(homeworks, list):
            logger.error(ERROR_MESSAGE_ISIN)
            raise ERROR_MESSAGE_ISIN
        if not homeworks:
            logger.debug(MESSEGE_DEBUG.format(current_date=current_date))
        return homeworks


def parse_status(homework):
    """Функция возвращает статус домашней работы."""
    ERROR_MESSAGE_API = 'В ответе API отсутствует ключ: {error}'
    ERROR_MESSAGE_STATUS = (
                'Статус {homework_status} '
                'домашней работы: {homework_name} не документирован.')
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError as error:
        logger.error(ERROR_MESSAGE_API.format(error=error))
        raise KeyError(ERROR_MESSAGE_API.format(error=error))
    else:
        if homework_status not in HOMEWORK_STATUSES:
            logger.error(ERROR_MESSAGE_STATUS.format(
                homework_status=homework_status,
                homework_name=homework_name)
            )
            raise KeyError(ERROR_MESSAGE_STATUS.format(
                homework_status=homework_status,
                homework_name=homework_name)
            )

        verdict = HOMEWORK_STATUSES[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет наличие всех необходимых токенов для работы программы."""
    ERROR_CRITICAL = ('Отсутствует обязательная переменная окружения:'
                      ' {token_name}')
    tokens_dict = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for token_name, token in tokens_dict.items():
        if not token:
            logger.critical(ERROR_CRITICAL.format(token_name=token_name))
            return False
    return True


def main():
    """Основная логика работы бота."""
    ERROR_MESSAGE = 'Сбой в работе программы: {error}'
    if not check_tokens():
        sys.exit(1)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)
            time.sleep(RETRY_TIME)
        except Exception as error:
            logger.error(ERROR_MESSAGE.format(error=error))
            if last_error != ERROR_MESSAGE.format(error=error):
                last_error = ERROR_MESSAGE.format(error=error)
                send_message(bot, ERROR_MESSAGE.format(error=error))
            time.sleep(RETRY_TIME)
        else:
            current_timestamp = response['current_date']


if __name__ == '__main__':
    main()
