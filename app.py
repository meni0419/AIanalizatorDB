# !/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import json
import time
import markdown
from pathlib import Path
import threading
import queue
import uuid
from contextlib import contextmanager

from config import Config
from deepseek_helpers import DeepSeekChatPersistent
from database import ChatDatabase, UserDatabase

app = Flask(__name__)
app.config.from_object(Config)

# Настройка для работы за прокси
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

Session(app)

# Глобальные объекты
# chat_instance = None
# chat_lock = threading.Lock()
# Вместо одного глобального экземпляра - словарь по пользователям
user_chat_instances = {}
chat_lock = threading.Lock()
db = ChatDatabase()
user_db = UserDatabase()
# Глобальные переменные для асинхронных операций
async_operations = {}
operation_lock = threading.Lock()


class AsyncOperation:
    def __init__(self, operation_id):
        self.operation_id = operation_id
        self.status = "pending"  # pending, running, completed, error
        self.progress = ""
        self.result = None
        self.error = None
        self.start_time = time.time()


def get_chat_instance():
    """Получает экземпляр чата для конкретного пользователя"""
    global user_chat_instances

    # Проверяем, находимся ли мы в контексте запроса
    try:
        user_id = session.get('user_id')
    except RuntimeError:
        # Если нет контекста запроса, возвращаем глобальный экземпляр
        global chat_instance
        with chat_lock:
            if chat_instance is None:
                chat_instance = DeepSeekChatPersistent(
                    model_name=app.config['DEEPSEEK_MODEL'],
                    max_context_tokens=app.config['MAX_CONTEXT_TOKENS']
                )
            return chat_instance

    if not user_id:
        raise Exception("Пользователь не авторизован")

    with chat_lock:
        if user_id not in user_chat_instances:
            user_chat_instances[user_id] = DeepSeekChatPersistent(
                model_name=app.config['DEEPSEEK_MODEL'],
                max_context_tokens=app.config['MAX_CONTEXT_TOKENS']
            )
        return user_chat_instances[user_id]


# Добавляем функцию очистки неактивных пользователей
def cleanup_inactive_users():
    """Очищает экземпляры чата неактивных пользователей"""
    while True:
        time.sleep(3600)  # Каждый час
        with chat_lock:
            # Здесь можно добавить логику удаления неактивных пользователей
            # Например, если пользователь не активен больше 2 часов
            pass


cleanup_thread = threading.Thread(target=cleanup_inactive_users)
cleanup_thread.daemon = True
cleanup_thread.start()


def get_session_id():
    """Получение ID сессии"""
    if 'session_id' not in session or not session['session_id']:
        session_id = user_db.create_session(session['user_id'])
        session['session_id'] = session_id
    return session['session_id']


def allowed_file(filename):
    """Проверяет, разрешено ли расширение файла"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def read_file_content(file_path):
    """Читает содержимое файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        for encoding in ['cp1251', 'latin1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except:
                continue
        return "[ОШИБКА: Не удалось прочитать файл - неподдерживаемая кодировка]"
    except Exception as e:
        return f"[ОШИБКА при чтении файла: {str(e)}]"


@app.route('/')
def index():
    """Главная страница - перенаправление на чат или логин"""
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Пожалуйста, заполните все поля', 'error')
            return render_template('login.html')

        user_id = user_db.verify_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            session['logged_in'] = True

            # Создаем новую сессию чата
            session_id = user_db.create_session(user_id)
            session['session_id'] = session_id

            flash('Успешная авторизация', 'success')
            return redirect(url_for('chat'))
        else:
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/chat')
def chat():
    """Страница чата"""
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('login'))

    chat_inst = get_chat_instance()
    model_loaded = chat_inst.model_loaded

    return render_template('chat.html',
                           username=session['username'],
                           model_loaded=model_loaded,
                           model_name=app.config['DEEPSEEK_MODEL'])


@app.route('/get_history', methods=['GET'])
def get_history():
    """Получить историю сообщений"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        session_id = get_session_id()
        messages = db.get_messages(session_id)
        return jsonify({
            'success': True,
            'messages': messages
        })
    except Exception as e:
        return jsonify({'error': f'Ошибка получения истории: {str(e)}'}), 500


@app.route('/preload_model', methods=['POST'])
def preload_model():
    """Предзагрузка модели в память"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        chat_inst = get_chat_instance()

        if chat_inst.model_loaded:
            return jsonify({
                'success': True,
                'message': 'Модель уже загружена в память'
            })

        print("🔄 Запускаю предзагрузку модели...")
        print("⏱️ Это может занять очень много времени для больших моделей на CPU...")

        # Загружаем модель БЕЗ каких-либо таймаутов
        start_time = time.time()
        success = chat_inst.preload_model()
        load_time = time.time() - start_time

        print(f"⏱️ Общее время загрузки: {load_time:.2f} секунд ({load_time / 60:.2f} минут)")

        if success:
            return jsonify({
                'success': True,
                'message': f'Модель загружена за {load_time:.2f} секунд',
                'load_time': round(load_time, 2)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Не удалось загрузить модель'
            }), 500

    except Exception as e:
        error_msg = f"Ошибка при загрузке модели: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()

        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


@app.route('/send_message', methods=['POST'])
def send_message():
    """Отправка сообщения в чат"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        # Читаем данные из form
        if request.content_type and 'multipart/form-data' in request.content_type:
            message = request.form.get('message', '').strip()
            session_id = request.form.get('session_id', '')

            # Обрабатываем файлы
            files_content = []
            uploaded_files = request.files.getlist('files')

            for file in uploaded_files:
                if file and file.filename:
                    if allowed_file(file.filename):
                        try:
                            content = file.read().decode('utf-8')
                            files_content.append({
                                'name': file.filename,
                                'content': content
                            })
                        except UnicodeDecodeError:
                            file.seek(0)
                            try:
                                content = file.read().decode('cp1251')
                                files_content.append({
                                    'name': file.filename,
                                    'content': content
                                })
                            except:
                                files_content.append({
                                    'name': file.filename,
                                    'content': f'[ОШИБКА: Не удалось прочитать файл - неподдерживаемая кодировка]'
                                })
                    else:
                        return jsonify({'error': f'Неподдерживаемый тип файла: {file.filename}'}), 400
        else:
            data = request.get_json()
            message = data.get('message', '').strip()
            session_id = data.get('session_id', '')
            files_content = data.get('files', [])

        if not message:
            return jsonify({'error': 'Пустое сообщение'}), 400

        chat_inst = get_chat_instance()

        if session_id:
            session['session_id'] = session_id
        else:
            session_id = get_session_id()

        if not chat_inst.model_loaded:
            return jsonify({'error': 'Модель не загружена. Используйте кнопку "Загрузить модель"'}), 400

        # Обрабатываем прикрепленные файлы
        original_message = message

        if files_content:
            file_texts = []
            for file_data in files_content:
                filename = file_data.get('name', 'unknown')
                content = file_data.get('content', '')

                if len(content) > 200000:
                    content = content[:200000] + "\n\n[... файл обрезан из-за большого размера ...]"

                file_text = f"[Файл: {filename}]\n"
                file_text += f"[Размер: {len(content)} символов]\n"
                file_text += "--- СОДЕРЖИМОЕ ФАЙЛА ---\n"
                file_text += content
                file_text += "\n--- КОНЕЦ ФАЙЛА ---\n\n"
                file_texts.append(file_text)

            message = ''.join(file_texts) + message

        # Сохраняем сообщение пользователя в БД
        db.save_message(session_id, 'user', original_message, files=files_content, user_id=session.get('user_id'))

        # Отправляем сообщение БЕЗ каких-либо таймаутов
        start_time = time.time()

        print(f"📤 Отправляю сообщение: {message[:100]}...")
        print("⏳ Ожидание ответа от модели (может занять несколько часов для CPU)...")

        # Простая отправка без таймаутов
        response = chat_inst.send_message(message)

        if isinstance(response, dict) and 'error' in response:
            return jsonify({'error': response['error']}), 500

        print(f"📥 Получен ответ: {response[:100]}...")

        response_time = time.time() - start_time

        # Обновление названия сессии
        messages_count = len(db.get_messages(session_id))
        if messages_count == 1:
            title = original_message[:50] + ('...' if len(original_message) > 50 else '')
            user_db.update_session_title(session_id, title)

        # Обрабатываем ответ
        thinking_text = ""
        final_response = response

        if "<think>" in response and "</think>" in response:
            import re
            thinking_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
            if thinking_match:
                thinking_text = thinking_match.group(1).strip()
                final_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

        if not final_response.strip():
            final_response = "Извините, произошла ошибка при обработке ответа."

        # Сохраняем ответ ассистента в БД
        db.save_message(session_id, 'assistant', final_response, thinking_text, response_time,
                        files=None, user_id=session.get('user_id'))

        # Создаем ответ
        response_data = {
            'success': True,
            'thinking': thinking_text,
            'response': final_response,
            'response_time': round(response_time, 2),
            'session_id': session_id
        }

        # Конвертируем markdown в HTML
        try:
            html_response = markdown.markdown(final_response, extensions=['codehilite', 'fenced_code', 'tables'])
            response_data['html_response'] = html_response
        except Exception as e:
            print(f"❌ Ошибка конвертации markdown: {str(e)}")
            response_data['html_response'] = final_response

        print(f"✅ Отправляю ответ в браузер: {len(final_response)} символов")
        print(f"⏱️ Общее время обработки: {response_time:.2f} секунд ({response_time / 60:.2f} минут)")

        # Возвращаем ответ
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

    except Exception as e:
        print(f"❌ Ошибка в send_message: {str(e)}")
        import traceback
        traceback.print_exc()

        error_response = jsonify({'error': f'Ошибка при отправке сообщения: {str(e)}'})
        error_response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return error_response, 500


@app.route('/upload_file', methods=['POST'])
def upload_file():
    """Загрузка файла"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не выбран'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)

            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)

            content = read_file_content(file_path)
            os.remove(file_path)

            return jsonify({
                'success': True,
                'filename': filename,
                'content': content,
                'size': len(content)
            })
        else:
            return jsonify({'error': 'Неподдерживаемый тип файла'}), 400

    except Exception as e:
        return jsonify({'error': f'Ошибка загрузки файла: {str(e)}'}), 500


@app.route('/clear_history', methods=['POST'])
def clear_history():
    """Очистка истории чата"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        chat_inst = get_chat_instance()
        session_id = get_session_id()

        chat_inst.clear_history()
        db.clear_session(session_id)

        return jsonify({'success': True, 'message': 'История очищена'})

    except Exception as e:
        return jsonify({'error': f'Ошибка очистки истории: {str(e)}'}), 500


@app.route('/get_status', methods=['GET'])
def get_status():
    """Получение статуса системы"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    try:
        chat_inst = get_chat_instance()
        session_id = get_session_id()

        current_tokens = chat_inst.get_context_size()
        used_percent = (current_tokens / chat_inst.max_context_tokens) * 100

        # Получаем статистику из БД
        stats = db.get_session_stats(session_id)

        return jsonify({
            'success': True,
            'model_loaded': chat_inst.model_loaded,
            'model_name': chat_inst.model_name,
            'current_tokens': current_tokens,
            'max_tokens': chat_inst.max_context_tokens,
            'used_percent': round(used_percent, 1),
            'messages_count': len(chat_inst.conversation_history),
            'db_stats': stats
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка получения статуса: {str(e)}'}), 500


@app.route('/get_sessions')
def get_sessions():
    """Получение всех сессий пользователя"""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Не авторизован'})

    try:
        user_id = session['user_id']
        sessions = user_db.get_user_sessions(user_id)

        return jsonify({'success': True, 'sessions': sessions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/load_session/<session_id>')
def load_session(session_id):
    """Загрузка конкретной сессии с восстановлением контекста"""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Не авторизован'})

    try:
        session['session_id'] = session_id
        messages = db.get_messages(session_id)

        # ВАЖНО: Восстанавливаем контекст в модели
        chat_inst = get_chat_instance()
        chat_inst.clear_history()  # Очищаем старый контекст

        # Загружаем историю в модель
        for msg in messages:
            if msg['role'] in ['user', 'assistant']:
                chat_inst.conversation_history.append({
                    "role": msg['role'],
                    "content": msg['content']
                })

        print(f"🔄 Восстановлен контекст: {len(chat_inst.conversation_history)} сообщений")

        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/new_chat', methods=['POST'])
def new_chat():
    """Создание нового чата"""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Не авторизован'})

    try:
        user_id = session['user_id']
        session_id = user_db.create_session(user_id)
        session['session_id'] = session_id

        # Очищаем контекст модели для нового чата
        chat_inst = get_chat_instance()
        chat_inst.clear_history()

        print("🆕 Создан новый чат, контекст очищен")

        return jsonify({'success': True, 'session_id': session_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/send_message_async', methods=['POST'])
def send_message_async():
    """Асинхронная отправка сообщения"""
    if 'logged_in' not in session or not session['logged_in']:
        return jsonify({'error': 'Не авторизован'}), 401

    # Создаем операцию
    operation_id = str(uuid.uuid4())
    operation = AsyncOperation(operation_id)

    with operation_lock:
        async_operations[operation_id] = operation

    # ВАЖНО: Сохраняем данные сессии ДО запуска потока
    user_id = session.get('user_id')
    current_session_id = session.get('session_id', '')

    # Получаем chat_instance ТУТ, в контексте запроса
    try:
        chat_inst = get_chat_instance()
    except Exception as e:
        operation.status = "error"
        operation.error = f"Ошибка получения чата: {str(e)}"
        return jsonify({'error': f'Ошибка получения чата: {str(e)}'}), 500

    # Получаем данные из запроса
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            message = request.form.get('message', '').strip()
            session_id = request.form.get('session_id', '')

            # Обрабатываем файлы
            files_content = []
            uploaded_files = request.files.getlist('files')

            for file in uploaded_files:
                if file and file.filename:
                    if allowed_file(file.filename):
                        try:
                            content = file.read().decode('utf-8')
                            files_content.append({
                                'name': file.filename,
                                'content': content
                            })
                        except:
                            files_content.append({
                                'name': file.filename,
                                'content': f'[ОШИБКА: Не удалось прочитать файл]'
                            })
        else:
            data = request.get_json()
            message = data.get('message', '').strip()
            session_id = data.get('session_id', '')
            files_content = data.get('files', [])

        if not message:
            operation.status = "error"
            operation.error = "Пустое сообщение"
            return jsonify({'error': 'Пустое сообщение'}), 400

    except Exception as e:
        operation.status = "error"
        operation.error = str(e)
        return jsonify({'error': f'Ошибка обработки запроса: {str(e)}'}), 400

    # Определяем финальный session_id
    if session_id:
        final_session_id = session_id
    else:
        if not current_session_id:
            final_session_id = user_db.create_session(user_id)
        else:
            final_session_id = current_session_id

    # Запускаем обработку в отдельном потоке
    def process_message():
        try:
            operation.status = "running"
            operation.progress = "Инициализация..."

            # НЕ ИСПОЛЬЗУЕМ session внутри потока - используем переданные переменные
            if not chat_inst.model_loaded:
                operation.status = "error"
                operation.error = "Модель не загружена. Используйте кнопку 'Загрузить модель'"
                return

            # Обрабатываем прикрепленные файлы
            original_message = message
            processed_message = message

            if files_content:
                operation.progress = "Обработка файлов..."
                file_texts = []
                for file_data in files_content:
                    filename = file_data.get('name', 'unknown')
                    content = file_data.get('content', '')

                    if len(content) > 200000:
                        content = content[:200000] + "\n\n[... файл обрезан ...]"

                    file_text = f"[Файл: {filename}]\n--- СОДЕРЖИМОЕ ---\n{content}\n--- КОНЕЦ ---\n\n"
                    file_texts.append(file_text)

                processed_message = ''.join(file_texts) + message

            # Сохраняем сообщение пользователя
            db.save_message(final_session_id, 'user', original_message, files=files_content, user_id=user_id)

            # Отправляем сообщение в AI
            operation.progress = "Ожидание ответа от AI..."
            start_time = time.time()

            response = chat_inst.send_message(processed_message)

            if isinstance(response, dict) and 'error' in response:
                operation.status = "error"
                operation.error = response['error']
                return

            response_time = time.time() - start_time

            # Обновление названия сессии
            messages_count = len(db.get_messages(final_session_id))
            if messages_count == 1:
                title = original_message[:50] + ('...' if len(original_message) > 50 else '')
                user_db.update_session_title(final_session_id, title)

            # Обрабатываем ответ
            thinking_text = ""
            final_response = response

            if "<think>" in response and "</think>" in response:
                import re
                thinking_match = re.search(r'<think>(.*?)</think>', response, re.DOTALL)
                if thinking_match:
                    thinking_text = thinking_match.group(1).strip()
                    final_response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

            if not final_response.strip():
                final_response = "Извините, произошла ошибка при обработке ответа."

            # Сохраняем ответ ассистента
            db.save_message(final_session_id, 'assistant', final_response, thinking_text, response_time,
                            files=None, user_id=user_id)

            # Результат операции
            operation.result = {
                'success': True,
                'thinking': thinking_text,
                'response': final_response,
                'response_time': round(response_time, 2),
                'session_id': final_session_id
                # НЕ включаем 'user_message' - оно уже показано в UI
            }

            operation.status = "completed"
            operation.progress = "Готово"

        except Exception as e:
            operation.status = "error"
            operation.error = str(e)
            print(f"❌ Ошибка в асинхронной обработке: {str(e)}")
            import traceback
            traceback.print_exc()

    # Запускаем поток
    thread = threading.Thread(target=process_message)
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'operation_id': operation_id,
        'message': 'Сообщение принято в обработку'
    })


@app.route('/operation_status/<operation_id>', methods=['GET'])
def operation_status(operation_id):
    """Проверка статуса асинхронной операции"""
    with operation_lock:
        operation = async_operations.get(operation_id)

        if not operation:
            return jsonify({'error': 'Операция не найдена'}), 404

        elapsed_time = time.time() - operation.start_time

        response = {
            'operation_id': operation_id,
            'status': operation.status,
            'progress': operation.progress,
            'elapsed_time': round(elapsed_time, 2)
        }

        if operation.status == "completed":
            response['result'] = operation.result
        elif operation.status == "error":
            response['error'] = operation.error

        return jsonify(response)


@app.route('/delete_session/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Удаление сессии"""
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Не авторизован'}), 401

    try:
        # Проверяем, что сессия принадлежит текущему пользователю
        user_id = session.get('user_id')
        sessions = user_db.get_user_sessions(user_id)

        # Найдем сессию среди пользовательских сессий
        session_exists = any(s['session_id'] == session_id for s in sessions)

        if not session_exists:
            return jsonify({'success': False, 'error': 'Сессия не найдена или не принадлежит вам'}), 404

        print(f"🗑️ Удаляем сессию {session_id} для пользователя {user_id}")

        # Удаляем сессию из базы данных
        user_db.delete_session(session_id)

        # Если удаляем текущую активную сессию, сбрасываем её
        if session.get('session_id') == session_id:
            session.pop('session_id', None)
            # Очищаем историю чата в памяти
            chat_inst = get_chat_instance()
            chat_inst.clear_history()
            print("🧹 Очищена история в памяти")

        return jsonify({'success': True, 'message': 'Сессия удалена'})

    except Exception as e:
        print(f"❌ Ошибка удаления сессии {session_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'Ошибка удаления сессии: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(
        debug=app.config['DEBUG'],
        host=app.config['SERVER_HOST'],
        port=app.config['SERVER_PORT'],
        threaded=True
    )
