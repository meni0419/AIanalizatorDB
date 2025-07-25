#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ollama
import os
import re
import sys
import time
from pathlib import Path


class DeepSeekChatPersistent:
    def __init__(self, model_name="deepseek-r1:8b", max_context_tokens=128000):
        self.model_name = model_name
        self.client = ollama.Client()
        self.conversation_history = []
        self.max_context_tokens = max_context_tokens
        self.model_loaded = False

    def preload_model(self):
        """Предварительная загрузка модели в память"""
        print(f"🔄 Загружаю модель {self.model_name} в память...")
        print("⏱️  Это может занять несколько минут для больших моделей...")

        try:
            # Отправляем простой запрос для загрузки модели
            start_time = time.time()

            response = self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "Привет! Скажи только 'Готов к работе!'"}],
                options={
                    "temperature": 0.1,
                    "num_ctx": 131072,
                    "keep_alive": "72h",  # Держать модель в памяти 24 часа
                }
            )

            load_time = time.time() - start_time
            print(f"✅ Модель загружена за {load_time:.2f} секунд")
            print(f"🤖 Ответ модели: {response['message']['content']}")

            self.model_loaded = True
            return True

        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {str(e)}")
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
        """Управляет размером контекста, удаляя старые сообщения"""
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

            # Ограничение для больших моделей - меньше размер файла
            max_file_size = 5 * 1024 * 1024  # 5MB для больших моделей
            if path.stat().st_size > max_file_size:
                return f"[ОШИБКА: Файл '{file_path}' слишком большой (>{max_file_size // 1024 // 1024}MB)]"

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            content_tokens = self.estimate_tokens(content)
            if content_tokens > self.max_context_tokens * 0.6:  # 60% от контекста
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
        pattern = r'#file:([^\s]+)'

        def replace_file_ref(match):
            file_path = match.group(1)
            return self.load_file_content(file_path)

        processed_text = re.sub(pattern, replace_file_ref, text)
        return processed_text

    def send_message(self, message):
        """Отправляет сообщение в DeepSeek"""
        if not self.model_loaded:
            print("❌ Модель не загружена! Используйте /preload")
            return "Модель не загружена в память"

        try:
            # Упрощенная обработка файлов
            if "#file:" in message:
                processed_message = self.process_file_references(message)
            else:
                processed_message = message

            self.conversation_history.append({
                "role": "user",
                "content": processed_message
            })

            self.manage_context()

            # Засекаем время ответа
            start_time = time.time()

            print(f"🔄 Отправляю запрос в модель...")

            # Убираем все таймауты для ollama - пусть работает сколько нужно
            response = self.client.chat(
                model=self.model_name,
                messages=self.conversation_history,
                options={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_ctx": 131072,
                    "keep_alive": "72h",  # Держим модель дольше
                }
            )

            response_time = time.time() - start_time

            assistant_response = response['message']['content']

            # Сохраняем ответ в истории
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_response
            })

            print(f"⏱️  Время ответа: {response_time:.2f} секунд ({response_time / 60:.2f} минут)")
            print(f"📊 Длина ответа: {len(assistant_response)} символов")

            return assistant_response

        except Exception as e:
            error_msg = f"Ошибка при отправке сообщения: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg

    def unload_model(self):
        """Выгружает модель из памяти """
        try:
            print("🔄 Выгружаю модель из памяти...")

            # Устанавливаем keep_alive в 0 для немедленной выгрузки
            self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "bye"}],
                options={"keep_alive": 0}
            )

            self.model_loaded = False
            print("✅ Модель выгружена из памяти")

        except Exception as e:
            print(f"❌ Ошибка выгрузки модели: {str(e)}")

    def clear_history(self):
        """Очищает историю разговора"""
        self.conversation_history = []
        print("✅ История разговора очищена")
        print(f"📊 Доступно токенов: {self.max_context_tokens}")

    def show_status(self):
        """Показывает статус контекста и модели"""
        current_tokens = self.get_context_size()
        used_percent = (current_tokens / self.max_context_tokens) * 100

        print(f"\n📊 Статус системы:")
        print(f"  Модель: {self.model_name}")
        print(f"  Статус модели: {'🟢 Загружена в память' if self.model_loaded else '🔴 Не загружена'}")
        print(f"  Использовано: {current_tokens:,} токенов ({used_percent:.1f}%)")
        print(f"  Доступно: {self.max_context_tokens - current_tokens:,} токенов")
        print(f"  Сообщений в истории: {len(self.conversation_history)}")

        if used_percent > 80:
            print("  ⚠️  Контекст почти заполнен!")
        elif used_percent > 60:
            print("  ⚡ Контекст активно используется")
        else:
            print("  ✅ Контекст в норме")

    def show_history(self):
        """Показывает историю разговора"""
        if not self.conversation_history:
            print("История разговора пуста")
            return

        print("\n--- ИСТОРИЯ РАЗГОВОРА ---")
        for i, msg in enumerate(self.conversation_history, 1):
            role = "👤 Вы" if msg["role"] == "user" else "🤖 AI"
            content = msg["content"]
            tokens = self.estimate_tokens(content)

            if len(content) > 200:
                content = content[:200] + "..."

            print(f"{i}. {role} (~{tokens} токенов): {content}")
        print("--- КОНЕЦ ИСТОРИИ ---\n")

    def run(self):
        """Запускает интерактивный чат"""
        print("🚀 DeepSeek-R1 Persistent Chat запущен!")
        print("📁 Для загрузки файла используйте: #file:путь_к_файлу")
        print("💬 Команды:")
        print("  /preload - загрузить модель в память")
        print("  /unload - выгрузить модель из памяти")
        print("  /clear - очистить историю")
        print("  /history - показать историю")
        print("  /status - статус системы")
        print("  /exit - выход")
        print("  /help - помощь")
        print("-" * 50)
        print("⚠️  Для работы с большими моделями сначала используйте /preload")

        while True:
            try:
                user_input = input("\n👤 Вы: ").strip()

                if not user_input:
                    continue

                if user_input.lower() == "/exit":
                    if self.model_loaded:
                        print("🔄 Выгружаю модель перед выходом...")
                        self.unload_model()
                    print("👋 До свидания!")
                    break
                elif user_input.lower() == "/preload":
                    if self.model_loaded:
                        print("✅ Модель уже загружена в память")
                    else:
                        self.preload_model()
                    continue
                elif user_input.lower() == "/unload":
                    if self.model_loaded:
                        self.unload_model()
                    else:
                        print("❌ Модель уже выгружена")
                    continue
                elif user_input.lower() == "/clear":
                    self.clear_history()
                    continue
                elif user_input.lower() == "/history":
                    self.show_history()
                    continue
                elif user_input.lower() == "/status":
                    self.show_status()
                    continue
                elif user_input.lower() == "/help":
                    print("\n📖 Помощь:")
                    print("  /preload - загрузить модель в память (обязательно для больших моделей)")
                    print("  /unload - выгрузить модель из памяти (освободить RAM)")
                    print("  #file:data.csv - загрузить файл в разговор")
                    print("  /clear - очистить историю разговора")
                    print("  /history - показать историю разговора")
                    print("  /status - показать статус системы и контекста")
                    print("  /exit - выход с автоматической выгрузкой модели")
                    continue

                if not self.model_loaded:
                    print("❌ Модель не загружена! Используйте /preload для загрузки")
                    continue

                print("🤖 DeepSeek думает...")
                response = self.send_message(user_input)
                print(f"\n🤖 AI: {response}")

            except KeyboardInterrupt:
                print("\n\n🔄 Выгружаю модель перед выходом...")
                if self.model_loaded:
                    self.unload_model()
                print("👋 Чат прерван пользователем. До свидания!")
                break
            except Exception as e:
                print(f"\n❌ Произошла ошибка: {str(e)}")
                print("Попробуйте еще раз или введите /exit для выхода")


def main():
    """Главная функция"""
    model_name = "deepseek-r1:8b"  # Можно изменить на любую модель

    chat = DeepSeekChatPersistent(model_name)
    chat.run()


if __name__ == "__main__":
    main()
