from typing import Dict
import logging
import os
import requests
import sys
import time

import telegram
from dotenv import load_dotenv
from http import HTTPStatus

import exceptions

load_dotenv()

# константы токенов практикума и телеграма
PRACTICUM_TOKEN: str = os.getenv("PRACTI_TOKEN")
TELEGRAM_TOKEN: str = os.getenv("TELE_TOKEN")
# константа  id чата телеграм
TELEGRAM_CHAT_ID: str = os.getenv("CHAT_ID")
# константа  интервала запроса
RETRY_PERIOD: int = 600
# константа  эндпоинта статуса домашней работы
ENDPOINT: str = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
# константа HTTP-заголовка
HEADERS: Dict[str, str] = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}
# константа TIME_INTERVA для подсчета секунд
# для основной функции(дни*часы*минуты*секунды)
TIME_INTERVAL: int = 30 * 24 * 60 * 60
# словарь статусов проверки дамашней работы
HOMEWORK_VERDICTS: Dict[str, str] = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)
log_handler = logging.StreamHandler()
logger.addHandler(log_handler)


def check_tokens():
    """Фунцкия проверяет доступность переменных окружения."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram чат.
    Также производит логирование статусов отправки
    """
    try:
        logging.info(f"Старт отправки сообщения: {message} в Telegram.")
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
    except telegram.error.TelegramError as error:
        logger.error(f"Ошибка отправки: {error}")
        raise exceptions.SendMessageError(f"Ошибка отправки: {error}")
    else:
        logging.debug(f' Сообщение: "{message}" успешно отправлено')


def get_api_answer(timestamp):
    """
    Функция делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    api_dict = {
        "url": ENDPOINT,
        "headers": HEADERS,
        "params": {"from_date": timestamp},
    }
    try:
        logging.info("параметр временной отметки:%s", api_dict["params"])
        homework_statuses = requests.get(**api_dict)
        if homework_statuses.status_code != HTTPStatus.OK:
            raise exceptions.ApiRequestError(
                f"Эндпоинт недоступен: {api_dict['url']}"
            )
        return homework_statuses.json()
    except requests.RequestException as error:
        raise exceptions.ApiRequestError(f"Ошибка запроса: {error}")


def check_response(response):
    """
    Функция проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if not isinstance(response, dict) or "homeworks" not in response:
        raise TypeError("Словарь в ответе API c домашними работами не найден")
    homeworks = response["homeworks"]
    if not isinstance(homeworks, list):
        raise TypeError("По ключу 'homeworks' не возвращается список")
    status = response["homeworks"][0].get("status")
    if status not in HOMEWORK_VERDICTS:
        raise TypeError(f"Ошибка: недокументированный статус: {status}")
    return homeworks[0]["status"]


def parse_status(homework):
    """Функция извлечения информации.
    Извлекает статус работы из информации
    о конкретной домашней работе.
    В качестве параметра функция получает только один элемент
    из списка домашних работ.
    Возвращает подготовленную для отправки в Telegram строку.
    """
    if "homework_name" not in homework:
        raise KeyError("В ответе API отсутствует ключ 'homework_name'")
    status = homework["status"]
    if status == "unknown":
        raise exceptions.HomeWorkStatusUnknown(
            "Статус домашней работы не задокументирован"
        )
    verdict = HOMEWORK_VERDICTS[status]
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f"Неидентифицированный статус: {status}")
    homework_name = homework["homework_name"]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """
    Логика работы бота.
    - Сделать запрос к API.
    - Проверить ответ.
    - При обновлении — получить статус работы из обновления
    и отправить сообщение в Telegram.
    - Снова сделать запрос к API спустя некоторое время
    """
    if not check_tokens():
        logging.critical("Отсутсвуют переменные окружения")
        sys.exit("Остановка работы бота, нужны переменные окружения.")
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - TIME_INTERVAL
    status = ""
    err_message = ""
    while True:
        try:
            response = get_api_answer(timestamp)
            get_status = check_response(response)
            if status == get_status:
                logger.debug("Статус не поменялся")
            else:
                status = get_status
                text = parse_status(response["homeworks"][0])
                send_message(bot, text)
        except Exception as error:
            if err_message != error:
                err_message = error
                message = f"В работе программы обнаружен сбой: {err_message}"
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
