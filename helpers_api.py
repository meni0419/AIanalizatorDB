from old.db_connect import get_db_connection
from typing import List, Dict, Any
import google.generativeai as genai
import os
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import concurrent.futures


try:
    from google.api_core.exceptions import TooManyRequests
except ImportError:
    TooManyRequests = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-1.5-pro-latest"

# Составляем список исключений для retry
retry_excepts = (TimeoutError, Exception)
if TooManyRequests:  # если доступно исключение, добавляем его
    retry_excepts = (TimeoutError, TooManyRequests, Exception)

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(retry_excepts),
    reraise=True
)
def safe_generate_content(model, prompt, timeout=200):
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(model.generate_content, prompt)
            return future.result(timeout=timeout)
    except Exception as e:
        print(f'Ошибка API: {e} (retry)')
        raise


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(5),
    reraise=True
)
def get_embedding(text):
    try:
        embedding = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )['embedding']
        return np.asarray(embedding)
    except Exception as e:
        print(f"Ошибка при получении эмбеддинга: {e} (retry)")
        raise

def cosine_sim(vec1, vec2):
    """Косинусное сходство между векторами"""
    vec1 = vec1.reshape(1, -1)
    vec2 = vec2.reshape(1, -1)
    return cosine_similarity(vec1, vec2)[0, 0]

def find_most_similar(query_text, candidates: list):
    """Возвращает самый похожий текст из списка candidates на query_text"""
    query_emb = get_embedding(query_text)
    max_score, best_text = -1, None
    for cand in candidates:
        cand_emb = get_embedding(cand)
        score = cosine_sim(query_emb, cand_emb)
        print(f"Сходство с '{cand}': {score:.3f}")
        if score > max_score:
            max_score, best_text = score, cand
    return best_text, max_score



def get_combined_data(indicator_id: str, period_start: str, period_end: str) -> List[Dict[str, Any]]:
    """Получает объединенные данные из БД одним запросом через SSH-туннель"""
    try:
        print(f"Подключаемся к базе данных...")
        with get_db_connection() as connection:
            print(f"Подключение установлено!")
            # Для pymysql не нужно указывать dictionary=True,
            # так как мы уже настроили DictCursor в подключении
            cursor = connection.cursor()

            query = """
                    SELECT u.user_id,
                           u.last_name,
                           u.first_name,
                           u.middle_name,
                           itm.indicator_to_mo_id,
                           itm.indicator_id,
                           itm.mo_id,
                           cpv.period_start,
                           cpv.period_end,
                           cpv.fact,
                           cpv.`result`
                    FROM closed_period_values cpv
                             JOIN indicator_to_mo itm ON itm.indicator_to_mo_id = cpv.indicator_to_mo_id
                             JOIN user_to_mo utm ON utm.mo_id = itm.mo_id
                             JOIN user u ON u.user_id = utm.user_id
                    WHERE itm.indicator_id = %s
                      AND cpv.period_start BETWEEN %s AND %s
                    """

            print(
                f"Выполняем запрос с параметрами: indicator_id={indicator_id}, period_start={period_start}, period_end={period_end}")
            cursor.execute(query, (indicator_id, period_start, period_end))
            results = cursor.fetchall()
            cursor.close()
            print(f"Найдено записей: {len(results)}")

        # Преобразуем fact в float (если он строка с запятой)
        for row in results:
            try:
                row['fact'] = float(row['fact'].replace(',', '.')) if isinstance(row['fact'], str) else float(
                    row['fact'])
            except (ValueError, TypeError, AttributeError):
                row['fact'] = None

            try:
                row['result'] = float(row['result'].replace(',', '.')) if isinstance(row['result'], str) else float(
                    row['result'])
            except (ValueError, TypeError, AttributeError):
                row['result'] = None

        valid_results = [row for row in results if row['fact'] is not None]
        print(f"Записей с корректными данными: {len(valid_results)}")
        return valid_results

    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        raise Exception(f"Ошибка при получении данных: {e}")


def format_data_to_csv(data: List[Dict[str, Any]]) -> str:
    """Форматирует данные в CSV строку"""
    if not data:
        return "Нет данных для анализа"

    # Заголовок CSV
    headers = "user_id,last_name,first_name,middle_name,indicator_to_mo_id,indicator_id,mo_id,period_start,period_end,fact,result"

    # Формируем строки данных
    csv_rows = []
    for row in data:
        csv_row = f"{row['user_id']},{row['last_name']},{row['first_name']},{row['middle_name']},{row['indicator_to_mo_id']},{row['indicator_id']},{row['mo_id']},{row['period_start']},{row['period_end']},{row['fact']},{row['result']}"
        csv_rows.append(csv_row)

    # Объединяем заголовок и данные
    return headers + "\n" + "\n".join(csv_rows)


# def analyze_data(data: List[Dict[str, Any]]='', prompt: str='') -> str:
def analyze_data(prompt: str) -> str:
    """Анализирует данные с помощью Gemini API"""
    # if not data:
    #     return "Не найдено данных для анализа. Проверьте параметры запроса."

    if not GEMINI_API_KEY:
        raise ValueError("API токен для Gemini не найден. Убедитесь, что переменная GEMINI_API_KEY установлена.")

    # print("Форматируем данные для анализа...")
    # data_csv = format_data_to_csv(data)

    data_description = """
    ## Структура данных:
    Каждая запись содержит:
    - user_id: Уникальный ID сотрудника
    - last_name: Фамилия
    - first_name: Имя  
    - middle_name: Отчество
    - fact: Числовое значение показателя (чем больше, тем лучше)
    - result: % выполнения показателя
    """

    # Создаем модель
    model = genai.GenerativeModel(MODEL_NAME)

    # Формируем промпт
    full_prompt = f"""
    {data_description}

    ИНСТРУКЦИИ (ОБЯЗАТЕЛЬНЫЕ К ВЫПОЛНЕНИЮ):
    1. Используй ТОЛЬКО эти данные:
    '{'data_csv'}'

    2. Формат ответа ДОЛЖЕН быть:
    - Только фамилии и значения fact
    - Без дополнительного текста
    - Без пояснений

    3. Если в запросе указано количество (например, топ-10) - выведи ровно столько

    4. Запрещено:
    - Изменять имена или значения
    - Добавлять несуществующие данные
    - Давать пояснения

    Запрос: {prompt}
    """

    simple_prompt = f"""{prompt}"""

    try:
        print("Отправляем запрос к Gemini API...")
        # response = model.generate_content(full_prompt)
        response = model.generate_content(simple_prompt)
        print("Получен ответ от Gemini API")
        return response.text
    except Exception as e:
        print(f"Ошибка при запросе к Gemini API: {e}")
        raise Exception(f"Ошибка при запросе к Gemini API: {e}")


def main():
    # Получение входных данных
    # custom_indicator_id = input("Какой показатель нужен для отчета: ")
    # custom_period_start = input("Период с (гггг-мм-дд): ")
    # custom_period_end = input("Период по (гггг-мм-дд): ")
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = input("Что хотите проанализировать: ")

    try:
        # Получаем объединенные данные одним запросом
        # combined_data = get_combined_data(custom_indicator_id, custom_period_start, custom_period_end)
        # Анализ данных
        # result = analyze_data(prompt)
        # print("\nРезультат анализа:")
        response = safe_generate_content(model, prompt)
        print("Ответ:", response.text)
        # print(result)

    except Exception as e:
        print(f"Ошибка: {e}")

    # Получить и сравнить эмбеддинги двух текстов
    text1 = "Пример первого текста"
    text2 = "Пример второго текста"
    emb1 = get_embedding(text1)
    emb2 = get_embedding(text2)
    sim = cosine_sim(emb1, emb2)
    print(f"Косинусное сходство: {sim:.3f}")

    # Поиск самого похожего текста
    candidates = ["Текст 1", "Текст о погоде", "Это пример первого текста", "Разный контент"]
    query = "Пример первого текста"
    best, score = find_most_similar(query, candidates)
    print(f"Самый похожий текст: '{best}' (сходство {score:.3f})")


if __name__ == "__main__":
    main()
