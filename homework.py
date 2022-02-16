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

# Здесь задана глобальная конфигурация для всех логгеров
logging.basicConfig(
    level=logging.DEBUG,
    filename='bot.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)

logger = logging.getLogger(__name__)
# Устанавливаем уровень, с которого логи будут сохраняться в файл
logger.setLevel(logging.INFO)
# Указываем обработчик логов
handler = RotatingFileHandler('my_logger.log',
                              maxBytes=50000000,
                              backupCount=5)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def send_message(bot, message):
    """Функция отправки сообщения ботом в чат TELEGRAM_CHAT_ID."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=message)
        logger.info(f'Бот отправил сообщение: {message}')
    except telegram.TelegramError as error:
        logger.error('Не удалось отправить сообщение пользователю!')
        raise error


def get_api_answer(current_timestamp):
    """Получает ответ от API-сервиса и преобразует его в тип данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_status = requests.get(ENDPOINT, headers=HEADERS,
                                       params=params)
    except requests.RequestException as error:
        error_message = (f'API не отвечает, при обращении к {ENDPOINT} '
                         f'код ошибки: {error}'
                         )
        logger.error(error_message)
        raise error
    if homework_status.status_code != HTTPStatus.OK:
        message = ('Код ответа не соответствует ожидаемому '
                   f'при запросе к {ENDPOINT}')
        logger.error(message)
        raise ValueError(message)
    return homework_status.json()


def check_response(response):
    """Функция проверки на корректный ответ от API.
    Возвращает список домашних работ."""
    try:
        homeworks = response['homeworks']
        current_date = response['current_date']
    except KeyError as error:
        error_message = 'Искомых ключей в ответе запроса API не найдено'
        logger.error(error_message)
        raise error
    else:
        if not isinstance(homeworks, list):
            error_message = ('Под ключом "homeworks" в ответ приходит'
                             'недопустимый тип данных')
            logger.error(error_message)
            raise error_message
        if not homeworks:
            message_debug = ('Статус ваших домашних работ со времени' 
                             f' {current_date} не изменился.')
            logger.debug(message_debug)
        return homeworks


def parse_status(homework):
    """Функция возвращает статус домашней работы."""
    try:
        homework_name = homework.get('homework_name')
        homework_status = homework.get('status')
    except KeyError as error:
        error_message = f'В ответе API отсутствует ключ: {error}'
        logger.error(error_message)
        raise KeyError(error_message)
    else:
        if homework_status not in HOMEWORK_STATUSES:
            error_message = (
                f'Статус {homework_status} '
                f'домашней работы: {homework_name} не документирован.')
            logger.error(error_message)
            raise KeyError(error_message)

        verdict = HOMEWORK_STATUSES.get(homework_status)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Функция проверяет наличие всех необходимых токенов для работы программы.
    """
    tokens_dict = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for token_name, token in tokens_dict.items():
        if not token:
            logger.critical(
                f'Отсутствует обязательная переменная окружения: {token_name}'
            )
            return False
    return True


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        sys.exit(1)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)
            time.sleep(RETRY_TIME)
        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)
            send_message(bot, error_message)
            time.sleep(RETRY_TIME)
        else:
            current_timestamp = response.get('current_date')


if __name__ == '__main__':
    main()
