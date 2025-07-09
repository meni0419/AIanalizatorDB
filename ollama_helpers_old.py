import ollama
from ollama import Client
from db_connect import get_db_connection
import re
import json
import time
import os
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import calendar

client = Client(host='http://localhost:11434')


class SmartDatabaseAgent:
    def __init__(self):
        self.schema = self.load_schema()
        self.query_patterns = self.setup_query_patterns()
        self.debug_mode = True  # Для отладки

    def load_schema(self) -> Dict:
        """Загружает схему БД из файла"""
        schema_file = 'db_schema.json'
        if not os.path.exists(schema_file):
            raise FileNotFoundError(f"Файл схемы БД '{schema_file}' не найден")

        with open(schema_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def setup_query_patterns(self) -> Dict:
        """Определяет паттерны запросов для автоматического распознавания"""
        return {
            'top_performers': {
                'keywords': ['топ', 'лучшие', 'самые эффективные', 'лидеры'],
                'template': 'top_employees'
            },
            'employee_dynamics': {
                'keywords': ['динамика', 'результаты', 'по месяцам', 'помесячно', 'факты помесячно'],
                'template': 'employee_dynamics'
            },
            'plan_analysis': {
                'keywords': ['план', 'перевыполня', 'недовыполня', 'выполнение плана', 'чаще всех перевыполнял'],
                'template': 'plan_analysis'
            },
            'worst_performers': {
                'keywords': ['худшие', 'плохие результаты', 'низкие показатели'],
                'template': 'worst_performers'
            },
            'period_comparison': {
                'keywords': ['сравнение', 'сравнить', 'за период', 'между'],
                'template': 'period_comparison'
            }
        }

    def analyze_query_intent(self, prompt: str) -> Tuple[str, Dict]:
        """Анализирует намерение пользователя и извлекает параметры"""
        prompt_lower = prompt.lower()

        # Извлекаем параметры
        params = {
            'employee_names': self.extract_employee_names(prompt),
            'indicator_id': self.extract_indicator_id(prompt),
            'date_range': self.extract_date_range(prompt),
            'limit': self.extract_limit(prompt),
            'order_by': self.extract_order_preference(prompt)
        }

        if self.debug_mode:
            print(f"🔍 Анализ запроса: {prompt}")
            print(f"📊 Параметры: {params}")

        # Определяем тип запроса
        for pattern_name, pattern_info in self.query_patterns.items():
            if any(keyword in prompt_lower for keyword in pattern_info['keywords']):
                if self.debug_mode:
                    print(f"🎯 Найден паттерн: {pattern_name} -> {pattern_info['template']}")
                return pattern_info['template'], params

        # По умолчанию - топ сотрудников
        if self.debug_mode:
            print("🎯 Использован паттерн по умолчанию: top_employees")
        return 'top_employees', params

    def extract_employee_names(self, prompt: str) -> List[str]:
        """Извлекает имена сотрудников из запроса"""
        names = []
        # Ищем паттерны типа "Иванов", "Петров Иван", "Сидорова Анна Петровна"
        name_patterns = [
            r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){0,2})',
            r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)',
        ]

        for pattern in name_patterns:
            matches = re.findall(pattern, prompt)
            names.extend(matches)

        return list(set(names))

    def extract_indicator_id(self, prompt: str) -> int:
        """Извлекает ID показателя из запроса"""
        match = re.search(r'показател[юьи]\s*(\d+)', prompt.lower())
        return int(match.group(1)) if match else 1

    def extract_date_range(self, prompt: str) -> Dict:
        """Извлекает временной диапазон из запроса"""
        prompt_lower = prompt.lower()

        # Извлекаем год
        year_match = re.search(r'(\d{4})', prompt)
        year = int(year_match.group(1)) if year_match else 2022

        # Определяем месяцы
        months = {
            'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4, 'май': 5, 'мая': 5,
            'июн': 6, 'июл': 7, 'август': 8, 'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12
        }

        found_months = []
        for month_name, month_num in months.items():
            if month_name in prompt_lower:
                found_months.append(month_num)

        # Если найден один месяц
        if len(found_months) == 1:
            month = found_months[0]
            return {
                'start': f"{year}-{month:02d}-01",
                'end': f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}",
                'type': 'month'
            }

        # Если диапазон "с января по декабрь"
        if 'по' in prompt_lower and len(found_months) == 2:
            start_month, end_month = min(found_months), max(found_months)
            return {
                'start': f"{year}-{start_month:02d}-01",
                'end': f"{year}-{end_month:02d}-{calendar.monthrange(year, end_month)[1]}",
                'type': 'range'
            }

        # По умолчанию - весь год
        return {
            'start': f"{year}-01-01",
            'end': f"{year}-12-31",
            'type': 'year'
        }

    def extract_limit(self, prompt: str) -> int:
        """Извлекает лимит записей"""
        match = re.search(r'(\d+)', prompt)
        return int(match.group(1)) if match else 10

    def extract_order_preference(self, prompt: str) -> str:
        """Определяет предпочтение сортировки"""
        prompt_lower = prompt.lower()
        if any(word in prompt_lower for word in ['худшие', 'плохие', 'низкие']):
            return 'ASC'
        return 'DESC'

    def generate_sql_by_template(self, template: str, params: Dict) -> str:
        """Генерирует SQL на основе шаблона и параметров"""

        if template == 'top_employees':
            return self.build_top_employees_query(params)
        elif template == 'employee_dynamics':
            return self.build_employee_dynamics_query(params)
        elif template == 'plan_analysis':
            return self.build_plan_analysis_query(params)
        elif template == 'worst_performers':
            return self.build_worst_performers_query(params)
        elif template == 'period_comparison':
            return self.build_period_comparison_query(params)
        else:
            return self.build_top_employees_query(params)

    def build_top_employees_query(self, params: Dict) -> str:
        """Строит запрос для топ сотрудников"""
        date_range = params['date_range']
        indicator_id = params['indicator_id']
        limit = params['limit']
        order = params['order_by']

        sql = f"""
        SELECT 
            u.last_name,
            u.first_name,
            cpv.fact,
            cpv.plan,
            cpv.result,
            cpv.period_start,
            cpv.period_end
        FROM user u
        JOIN user_to_mo utm ON u.user_id = utm.user_id
        JOIN indicator_to_mo itm ON utm.mo_id = itm.mo_id
        JOIN closed_period_values cpv ON itm.indicator_to_mo_id = cpv.indicator_to_mo_id
        WHERE itm.indicator_id = {indicator_id}
          AND cpv.period_start >= '{date_range['start']}'
          AND cpv.period_end <= '{date_range['end']}'
          AND cpv.fact IS NOT NULL
        ORDER BY cpv.fact {order}
        LIMIT {limit};
        """
        return sql.strip()

    def build_employee_dynamics_query(self, params: Dict) -> str:
        """Строит запрос для динамики сотрудника"""
        date_range = params['date_range']
        indicator_id = params['indicator_id']
        names = params['employee_names']

        name_condition = ""
        if names:
            name_parts = []
            for name in names:
                parts = name.split()
                if len(parts) >= 2:
                    name_parts.append(f"(u.last_name LIKE '%{parts[0]}%' AND u.first_name LIKE '%{parts[1]}%')")
                else:
                    name_parts.append(f"(u.last_name LIKE '%{parts[0]}%' OR u.first_name LIKE '%{parts[0]}%')")
            name_condition = f"AND ({' OR '.join(name_parts)})"

        sql = f"""
        SELECT 
            u.last_name,
            u.first_name,
            cpv.period_start,
            cpv.period_end,
            cpv.fact,
            cpv.plan,
            cpv.result,
            MONTH(cpv.period_start) as month,
            YEAR(cpv.period_start) as year
        FROM user u
        JOIN user_to_mo utm ON u.user_id = utm.user_id
        JOIN indicator_to_mo itm ON utm.mo_id = itm.mo_id
        JOIN closed_period_values cpv ON itm.indicator_to_mo_id = cpv.indicator_to_mo_id
        WHERE itm.indicator_id = {indicator_id}
          AND cpv.period_start >= '{date_range['start']}'
          AND cpv.period_end <= '{date_range['end']}'
          AND cpv.period_type = 1
          AND cpv.fact IS NOT NULL
          {name_condition}
        ORDER BY u.last_name, u.first_name, cpv.period_start;
        """
        return sql.strip()

    def build_plan_analysis_query(self, params: Dict) -> str:
        """Строит запрос для анализа выполнения планов"""
        date_range = params['date_range']
        indicator_id = params['indicator_id']

        sql = f"""
        SELECT 
            u.last_name,
            u.first_name,
            COUNT(*) as total_periods,
            COUNT(CASE WHEN cpv.result > 100 THEN 1 END) as overachieved_periods,
            COUNT(CASE WHEN cpv.result < 100 THEN 1 END) as underachieved_periods,
            AVG(cpv.result) as avg_result,
            AVG(cpv.fact) as avg_fact,
            AVG(cpv.plan) as avg_plan,
            ROUND(COUNT(CASE WHEN cpv.result > 100 THEN 1 END) * 100.0 / COUNT(*), 2) as overachievement_rate
        FROM user u
        JOIN user_to_mo utm ON u.user_id = utm.user_id
        JOIN indicator_to_mo itm ON utm.mo_id = itm.mo_id
        JOIN closed_period_values cpv ON itm.indicator_to_mo_id = cpv.indicator_to_mo_id
        WHERE itm.indicator_id = {indicator_id}
          AND cpv.period_start >= '{date_range['start']}'
          AND cpv.period_end <= '{date_range['end']}'
          AND cpv.fact IS NOT NULL
          AND cpv.plan IS NOT NULL
          AND cpv.result IS NOT NULL
        GROUP BY u.user_id, u.last_name, u.first_name
        HAVING COUNT(*) > 0
        ORDER BY overachievement_rate DESC, avg_result DESC
        LIMIT {params['limit']};
        """
        return sql.strip()

    def build_worst_performers_query(self, params: Dict) -> str:
        """Строит запрос для худших исполнителей"""
        params['order_by'] = 'ASC'
        return self.build_top_employees_query(params)

    def build_period_comparison_query(self, params: Dict) -> str:
        """Строит запрос для сравнения периодов"""
        return self.build_employee_dynamics_query(params)

    def get_best_plan_performer_dynamics(self, params: Dict) -> str:
        """Комбинированный запрос: находит лучшего по планам и показывает его динамику"""
        date_range = params['date_range']
        indicator_id = params['indicator_id']

        # Сначала найдем лучшего исполнителя планов
        best_performer_sql = f"""
        SELECT 
            u.last_name,
            u.first_name,
            COUNT(CASE WHEN cpv.result > 100 THEN 1 END) as overachieved_periods,
            ROUND(COUNT(CASE WHEN cpv.result > 100 THEN 1 END) * 100.0 / COUNT(*), 2) as overachievement_rate
        FROM user u
        JOIN user_to_mo utm ON u.user_id = utm.user_id
        JOIN indicator_to_mo itm ON utm.mo_id = itm.mo_id
        JOIN closed_period_values cpv ON itm.indicator_to_mo_id = cpv.indicator_to_mo_id
        WHERE itm.indicator_id = {indicator_id}
          AND cpv.period_start >= '{date_range['start']}'
          AND cpv.period_end <= '{date_range['end']}'
          AND cpv.fact IS NOT NULL
          AND cpv.plan IS NOT NULL
          AND cpv.result IS NOT NULL
        GROUP BY u.user_id, u.last_name, u.first_name
        HAVING COUNT(*) > 0
        ORDER BY overachievement_rate DESC, overachieved_periods DESC
        LIMIT 1;
        """
        return best_performer_sql

    def format_results_smart(self, results: List[Dict], template: str, params: Dict) -> str:
        """Умное форматирование результатов в зависимости от типа запроса"""
        if not results:
            return "📭 Данные не найдены"

        if template == 'employee_dynamics':
            return self.format_dynamics_results(results)
        elif template == 'plan_analysis':
            return self.format_plan_analysis_results(results)
        elif template in ['top_employees', 'worst_performers']:
            return self.format_top_employees_results(results, template == 'worst_performers')
        else:
            return self.format_generic_results(results)

    def format_dynamics_results(self, results: List[Dict]) -> str:
        """Форматирует результаты динамики"""
        if not results:
            return "📭 Данные не найдены"

        # Группируем по сотрудникам
        employees = {}
        for row in results:
            if isinstance(row, (tuple, list)):
                key = f"{row[0]} {row[1]}"
                if key not in employees:
                    employees[key] = []
                employees[key].append(row)

        response = ["📈 Динамика результатов по месяцам:\n"]

        for emp_name, emp_data in employees.items():
            response.append(f"👤 {emp_name}:")
            sorted_data = sorted(emp_data, key=lambda x: x[2])  # Сортируем по дате

            for row in sorted_data:
                if len(row) >= 9:
                    month = row[7]  # month
                    year = row[8]  # year
                    fact = row[4] if row[4] is not None else 'N/A'
                    plan = row[5] if row[5] is not None else 'N/A'
                    result = row[6] if row[6] is not None else 'N/A'

                    month_names = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                                   'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

                    response.append(f"   {month_names[month]} {year}: Факт={fact}, План={plan}, Результат={result}%")
            response.append("")

        return "\n".join(response)

    def format_plan_analysis_results(self, results: List[Dict]) -> str:
        """Форматирует результаты анализа планов"""
        response = ["📊 Анализ выполнения планов:\n"]

        for idx, row in enumerate(results, 1):
            if isinstance(row, (tuple, list)) and len(row) >= 9:
                name = f"{row[0]} {row[1]}"
                total = row[2]
                overachieved = row[3]
                underachieved = row[4]
                avg_result = row[5]
                overachievement_rate = row[8]

                response.append(f"{idx:2d}. {name:<25}")
                response.append(f"    📈 Перевыполнений: {overachieved}/{total} ({overachievement_rate}%)")
                response.append(f"    📉 Недовыполнений: {underachieved}/{total}")
                response.append(f"    📊 Средний результат: {avg_result:.2f}%")
                response.append("")

        return "\n".join(response)

    def format_top_employees_results(self, results: List[Dict], is_worst: bool = False) -> str:
        """Форматирует результаты топ сотрудников"""
        title = "📉 Худшие исполнители:" if is_worst else "📊 Топ сотрудников по эффективности:"
        response = [title]

        for idx, row in enumerate(results, 1):
            if isinstance(row, (tuple, list)) and len(row) >= 5:
                name = f"{row[0]} {row[1]}"
                fact = row[2] if row[2] is not None else 'N/A'
                plan = row[3] if row[3] is not None else 'N/A'
                result = row[4] if row[4] is not None else 'N/A'

                response.append(f"{idx:2d}. {name:<25} | Факт: {fact:>8} | План: {plan:>8} | Результат: {result:>8}%")

        return "\n".join(response)

    def format_generic_results(self, results: List[Dict]) -> str:
        """Общее форматирование результатов"""
        response = ["📄 Результаты запроса:"]
        for idx, row in enumerate(results, 1):
            response.append(f"{idx}. {row}")
        return "\n".join(response)

    def process_complex_query(self, prompt: str) -> str:
        """Обрабатывает сложные запросы с несколькими этапами"""
        prompt_lower = prompt.lower()

        # Проверяем, нужно ли выполнить комбинированный запрос
        if 'чаще всех перевыполнял' in prompt_lower and 'факты помесячно' in prompt_lower:
            return self.handle_best_performer_with_dynamics(prompt)

        return self.process_query(prompt)

    def handle_best_performer_with_dynamics(self, prompt: str) -> str:
        """Обрабатывает запрос: найти лучшего по планам и показать его динамику"""
        try:
            # Анализируем параметры
            _, params = self.analyze_query_intent(prompt)

            # Этап 1: Найти лучшего исполнителя планов
            best_performer_sql = self.get_best_plan_performer_dynamics(params)

            if self.debug_mode:
                print(f"🔍 SQL для поиска лучшего исполнителя:")
                print(best_performer_sql)

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(best_performer_sql)
                best_performer = cursor.fetchall()

            if not best_performer:
                return "📭 Не найден сотрудник с данными о выполнении планов"

            # Получаем имя лучшего исполнителя
            best_name = f"{best_performer[0][0]} {best_performer[0][1]}"

            # Этап 2: Получить динамику для этого сотрудника
            params['employee_names'] = [best_name]
            dynamics_sql = self.build_employee_dynamics_query(params)

            if self.debug_mode:
                print(f"🔍 SQL для динамики {best_name}:")
                print(dynamics_sql)

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(dynamics_sql)
                dynamics_results = cursor.fetchall()

            # Форматируем результат
            response = [f"🏆 Лучший исполнитель планов: {best_name}"]
            response.append(f"📈 Перевыполнений: {best_performer[0][2]} ({best_performer[0][3]}%)")
            response.append("")

            if dynamics_results:
                dynamics_formatted = self.format_dynamics_results(dynamics_results)
                response.append(dynamics_formatted)
            else:
                response.append("📭 Данные по динамике не найдены")

            return "\n".join(response)

        except Exception as e:
            return f"❌ Ошибка при обработке сложного запроса: {str(e)}"

    def process_query(self, prompt: str) -> str:
        """Обрабатывает запрос пользователя"""
        try:
            # Проверяем, нужна ли сложная обработка
            if 'чаще всех перевыполнял' in prompt.lower() and (
                    'факты помесячно' in prompt.lower() or 'помесячно' in prompt.lower()):
                return self.handle_best_performer_with_dynamics(prompt)

            # Анализируем намерение
            template, params = self.analyze_query_intent(prompt)

            # Генерируем SQL
            sql = self.generate_sql_by_template(template, params)

            if self.debug_mode:
                print(f"🔍 Сгенерированный SQL:")
                print(sql)

            # Выполняем запрос
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                results = cursor.fetchall()

            if self.debug_mode:
                print(f"📊 Получено результатов: {len(results)}")
                if results:
                    print(f"🔍 Первый результат: {results[0]}")

            # Форматируем результаты
            return self.format_results_smart(results, template, params)

        except Exception as e:
            return f"❌ Ошибка: {str(e)}"


def main():
    print("🤖 Инициализация умного SQL-ассистента...")
    try:
        agent = SmartDatabaseAgent()
        print("✅ Готово! Примеры запросов:")
        print("   • Покажи 10 самых эффективных сотрудников по показателю 1 за декабрь 2022")
        print("   • Динамика результатов Шпак Александра по показателю 1 с января по декабрь 2022")
        print("   • Кто регулярно перевыполняет план по показателю 1 за 2022 год")
        print("   • Худшие исполнители по показателю 1 за последний квартал 2022")
        print("\nВведите ваш запрос (или 'exit' для выхода):")

        while True:
            try:
                prompt = input("\n> ").strip()
                if prompt.lower() == 'exit':
                    print("👋 До свидания!")
                    break

                start_time = time.time()
                response = agent.process_query(prompt)
                elapsed = time.time() - start_time

                print(f"\n⏱️  Ответ ({elapsed:.2f} сек):")
                print(response)

            except KeyboardInterrupt:
                print("\n👋 Завершение работы...")
                break
            except Exception as e:
                print(f"❌ Ошибка: {str(e)}")

    except Exception as e:
        print(f"❌ Ошибка инициализации: {str(e)}")


if __name__ == "__main__":
    main()

    """
# CodeLlama модели
ollama pull codellama:7b
ollama pull codellama:13b
ollama pull codellama:34b

# Llama 2 модели
ollama pull llama2:7b
ollama pull llama2:13b
ollama pull llama2:70b

# Mistral модели
ollama pull mistral:7b
ollama pull mixtral:8x7b

# Gemma модели (от Google)
ollama pull gemma:2b
ollama pull gemma:7b

# Qwen модели
ollama pull qwen:7b
ollama pull qwen:14b
ollama pull qwen:72b

# DeepSeek модели
ollama pull deepseek-coder:6.7b
ollama pull deepseek-coder:33b
ollama pull deepseek-llm:7b

"""
# deepseek-llm:7b (врет), llama2:70b (нужно много памяти), llama2:13b, qwen:14b (200+ сек и сказал что нет данных), gemma:7b (120+ сек был ближе всех но выдал не максимальные R)
# в переданных данных найди 10 самых лучших сотрудников, лучшими считаются те у кого больше числов в поле факт и напиши мне фамилии этих сотрудников и их факты