#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import threading
from pathlib import Path


class DeepSeekAPIChat:
    def __init__(self, model_name="deepseek-r1:8b", max_context_tokens=128000, ollama_url="http://localhost:11434"):
        self.model_name = model_name
        self.ollama_url = ollama_url
        self.conversation_history = []
        self.max_context_tokens = max_context_tokens
        self.model_loaded = False
        self.lock = threading.Lock()

    def check_ollama_connection(self):
        """Проверяет подключение к Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def check_model_loaded(self):
        """Проверяет, загружена ли модель в память"""
        try:
            response = requests.get(f"{self.ollama_url}/api/ps", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                for model in models:
                    if model.get('name') == self.model_name:
                        self.model_loaded = True
                        return True
            self.model_loaded = False
            return False
        except Exception:
            self.model_loaded = False
            return False

    def preload_model(self):
        """Предварительная загрузка модели в память"""
        print(f"🔄 Загружаю модель {self.model_name} в память...")
        print("⏱️  Это может занять несколько минут для больших моделей...")

        try:
            start_time = time.time()

            # Отправляем запрос для загрузки модели
            payload = {
                "model": self.model_name,
                "prompt": "Привет! Скажи только 'Готов к работе!'",
                "stream": False,
                "keep_alive": "24h",  # Держим модель 24 часа
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 131072
                }
            }

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=300  # 5 минут таймаут для больших моделей
            )

            if response.status_code == 200:
                data = response.json()
                load_time = time.time() - start_time

                print(f"✅ Модель загружена за {load_time:.2f} секунд")
                print(f"🤖 Ответ модели: {data.get('response', 'Нет ответа')}")

                # Проверяем, что модель действительно загружена
                if self.check_model_loaded():
                    print("✅ Модель подтверждена в списке запущенных процессов")
                    return True
                else:
                    print("⚠️  Модель загружена, но не отображается в ollama ps")
                    self.model_loaded = True  # Устанавливаем вручную
                    return True
            else:
                print(f"❌ Ошибка загрузки модели: {response.status_code}")
                print(f"Ответ: {response.text}")
                return False

        except requests.exceptions.Timeout:
            print("❌ Таймаут при загрузке модели (5 минут)")
            return False
        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {str(e)}")
            return False

    def keep_model_alive(self):
        """Периодически пингует модель, чтобы она не выгружалась"""
        try:
            payload = {
                "model": self.model_name,
                "prompt": "ping",
                "stream": False,
                "keep_alive": "24h"
            }

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=30
            )

            return response.status_code == 200
        except Exception:
            return False

    def estimate_tokens(self, text):
        """Приблизительная оценка количества токенов"""
        return len(text) // 4

    def get_context_size(self):
        """Подсчитывает текущий размер контекста в токенах"""
        total_tokens = 0
        for msg in self.conversation_history:
            total_tokens += self.estimate_tokens(msg["content"])
        return total_tokens

    def manage_context(self):
        """Управляет размером контекста"""
        current_tokens = self.get_context_size()
        max_history_tokens = int(self.max_context_tokens * 0.8)

        if current_tokens > max_history_tokens:
            print(f"⚠️  Контекст переполнен ({current_tokens} токенов). Удаляю старые сообщения...")

            while len(self.conversation_history) > 2 and self.get_context_size() > max_history_tokens:
                self.conversation_history.pop(0)
                self.conversation_history.pop(0)

            print(f"✅ Контекст сжат до {self.get_context_size()} токенов")

        return current_tokens

    def load_file_content(self, file_path):
        """Загружает содержимое файла"""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"[ОШИБКА: Файл '{file_path}' не найден]"

            if not path.is_file():
                return f"[ОШИБКА: '{file_path}' не является файлом]"

            max_file_size = 5 * 1024 * 1024  # 5MB
            if path.stat().st_size > max_file_size:
                return f"[ОШИБКА: Файл '{file_path}' слишком большой (>5MB)]"

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            content_tokens = self.estimate_tokens(content)
            if content_tokens > self.max_context_tokens * 0.6:
                return f"[ОШИБКА: Файл '{file_path}' слишком большой ({content_tokens} токенов)]"

            file_info = f"[Файл: {file_path}]\n"
            file_info += f"[Размер: {len(content)} символов, ~{content_tokens} токенов]\n"
            file_info += "--- СОДЕРЖИМОЕ ФАЙЛА ---\n"
            file_info += content
            file_info += "\n--- КОНЕЦ ФАЙЛА ---"

            return file_info

        except UnicodeDecodeError:
            return f"[ОШИБКА: Не удалось прочитать файл '{file_path}' - возможно, это бинарный файл]"
        except Exception as e:
            return f"[ОШИБКА при чтении файла '{file_path}': {str(e)}]"

    def process_file_references(self, text):
        """Обрабатывает ссылки на файлы в тексте"""
        import re
        pattern = r'#file:([^\s]+)'

        def replace_file_ref(match):
            file_path = match.group(1)
            return self.load_file_content(file_path)

        processed_text = re.sub(pattern, replace_file_ref, text)
        return processed_text

    def send_message(self, message):
        """Отправляет сообщение в DeepSeek через API"""
        with self.lock:
            if not self.model_loaded:
                return {"error": "Модель не загружена! Используйте preload_model()"}

            try:
                # Обрабатываем ссылки на файлы
                processed_message = self.process_file_references(message)

                # Добавляем сообщение в историю
                self.conversation_history.append({
                    "role": "user",
                    "content": processed_message
                })

                # Управляем контекстом
                self.manage_context()

                # Формируем промпт с историей
                full_prompt = ""
                for msg in self.conversation_history:
                    role = "Human" if msg["role"] == "user" else "Assistant"
                    full_prompt += f"{role}: {msg['content']}\n\n"

                full_prompt += "Assistant: "

                # Отправляем запрос
                start_time = time.time()

                payload = {
                    "model": self.model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "keep_alive": "24h",
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_ctx": 131072
                    }
                }

                response = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                    timeout=300
                )

                response_time = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    assistant_response = data.get('response', 'Нет ответа')

                    # Добавляем ответ в историю
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": assistant_response
                    })

                    # Обрабатываем thinking блоки для DeepSeek-R1
                    thinking_text = ""
                    final_response = assistant_response

                    if "<thinking>" in assistant_response and "</thinking>" in assistant_response:
                        import re
                        thinking_match = re.search(r'<thinking>(.*?)</thinking>', assistant_response, re.DOTALL)
                        if thinking_match:
                            thinking_text = thinking_match.group(1).strip()
                            final_response = re.sub(r'<thinking>.*?</thinking>', '', assistant_response,
                                                    flags=re.DOTALL).strip()

                    return {
                        "success": True,
                        "thinking": thinking_text,
                        "response": final_response,
                        "response_time": round(response_time, 2),
                        "tokens_used": data.get('eval_count', 0),
                        "tokens_per_second": round(data.get('eval_count', 0) / response_time,
                                                   2) if response_time > 0 else 0
                    }
                else:
                    return {"error": f"Ошибка API: {response.status_code} - {response.text}"}

            except requests.exceptions.Timeout:
                return {"error": "Таймаут запроса (5 минут)"}
            except Exception as e:
                return {"error": f"Ошибка при отправке сообщения: {str(e)}"}

    def unload_model(self):
        """Выгружает модель из памяти"""
        try:
            print("🔄 Выгружаю модель из памяти...")

            payload = {
                "model": self.model_name,
                "keep_alive": 0  # Немедленная выгрузка
            }

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=30
            )

            self.model_loaded = False
            print("✅ Модель выгружена из памяти")
            return True

        except Exception as e:
            print(f"❌ Ошибка выгрузки модели: {str(e)}")
            return False

    def clear_history(self):
        """Очищает историю разговора"""
        self.conversation_history = []
        print("✅ История разговора очищена")

    def get_status(self):
        """Получает статус системы"""
        current_tokens = self.get_context_size()
        used_percent = (current_tokens / self.max_context_tokens) * 100

        # Проверяем статус модели
        model_status = self.check_model_loaded()

        return {
            "model_loaded": model_status,
            "model_name": self.model_name,
            "current_tokens": current_tokens,
            "max_tokens": self.max_context_tokens,
            "used_percent": round(used_percent, 1),
            "messages_count": len(self.conversation_history),
            "ollama_connected": self.check_ollama_connection()
        }


# Функция для CLI использования
def main():
    """Главная функция для CLI"""
    model_name = "deepseek-r1:8b"

    chat = DeepSeekAPIChat(model_name)

    # Проверяем подключение к Ollama
    if not chat.check_ollama_connection():
        print("❌ Ollama не запущен! Запустите: ollama serve")
        return

    print("🚀 DeepSeek-R1 API Chat запущен!")
    print("💬 Команды: /preload, /status, /clear, /exit")
    print("-" * 50)

    while True:
        try:
            user_input = input("\n👤 Вы: ").strip()

            if not user_input:
                continue

            if user_input.lower() == "/exit":
                if chat.model_loaded:
                    chat.unload_model()
                print("👋 До свидания!")
                break
            elif user_input.lower() == "/preload":
                chat.preload_model()
                continue
            elif user_input.lower() == "/status":
                status = chat.get_status()
                print(f"\n📊 Статус системы:")
                print(f"  Модель: {status['model_name']}")
                print(f"  Статус: {'🟢 Загружена' if status['model_loaded'] else '🔴 Не загружена'}")
                print(f"  Ollama: {'🟢 Подключен' if status['ollama_connected'] else '🔴 Не подключен'}")
                print(f"  Токены: {status['current_tokens']:,} / {status['max_tokens']:,} ({status['used_percent']}%)")
                print(f"  Сообщений: {status['messages_count']}")
                continue
            elif user_input.lower() == "/clear":
                chat.clear_history()
                continue

            if not chat.model_loaded:
                print("❌ Модель не загружена! Используйте /preload")
                continue

            print("🤖 DeepSeek думает...")
            result = chat.send_message(user_input)

            if result.get("success"):
                if result.get("thinking"):
                    print(f"\n🤔 Размышления: {result['thinking']}")
                print(f"\n🤖 AI: {result['response']}")
                print(f"⏱️  Время ответа: {result['response_time']}с | Токены/сек: {result['tokens_per_second']}")
            else:
                print(f"❌ Ошибка: {result.get('error')}")

        except KeyboardInterrupt:
            print("\n\n🔄 Выгружаю модель перед выходом...")
            if chat.model_loaded:
                chat.unload_model()
            print("👋 Чат прерван пользователем. До свидания!")
            break
        except Exception as e:
            print(f"\n❌ Произошла ошибка: {str(e)}")


if __name__ == "__main__":
    main()