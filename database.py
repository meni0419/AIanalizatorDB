import sqlite3
import json
import os
from datetime import datetime
from threading import Lock
import bcrypt
from werkzeug.security import generate_password_hash, check_password_hash


class ChatDatabase:
    def __init__(self, db_path="chat_history.db"):
        self.db_path = db_path
        self.lock = Lock()
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS chat_messages
                           (
                               id            INTEGER PRIMARY KEY AUTOINCREMENT,
                               session_id    TEXT NOT NULL,
                               role          TEXT NOT NULL,
                               content       TEXT NOT NULL,
                               thinking      TEXT,
                               response_time REAL,
                               timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
                               files         TEXT
                           )
                           ''')

            cursor.execute('''
                           CREATE INDEX IF NOT EXISTS idx_session_timestamp
                               ON chat_messages(session_id, timestamp)
                           ''')

            conn.commit()
            conn.close()

    def save_message(self, session_id, role, content, thinking="", response_time=0, files=None, user_id=None):
        """Сохранить сообщение в базу данных"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            files_json = json.dumps(files) if files else None

            cursor.execute('''
                           INSERT INTO chat_messages
                               (session_id, role, content, thinking, response_time, files, user_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ''', (session_id, role, content, thinking, response_time, files_json, user_id))

            # Обновляем время последнего обновления сессии
            cursor.execute('''
                           UPDATE chat_sessions
                           SET updated_at = CURRENT_TIMESTAMP
                           WHERE session_id = ?
                           ''', (session_id,))

            conn.commit()
            conn.close()

    def get_messages(self, session_id, limit=50):
        """Получить сообщения для сессии"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT role, content, thinking, response_time, timestamp, files, user_id
                           FROM chat_messages
                           WHERE session_id = ?
                           ORDER BY timestamp DESC
                           LIMIT ?
                           ''', (session_id, limit))

            messages = []
            for row in cursor.fetchall():
                role, content, thinking, response_time, timestamp, files_json, user_id = row
                files = json.loads(files_json) if files_json else []

                messages.append({
                    'role': role,
                    'content': content,
                    'thinking': thinking or '',
                    'response_time': response_time or 0,
                    'timestamp': timestamp,
                    'files': files,
                    'user_id': user_id
                })

            conn.close()
            return list(reversed(messages))  # Возвращаем в хронологическом порядке

    def clear_session(self, session_id):
        """Очистить историю сессии"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))

            conn.commit()
            conn.close()

    # В класс ChatDatabase добавить:
    def delete_session_messages(self, session_id):
        """Удаление всех сообщений сессии"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))
            conn.commit()
            conn.close()

    def get_session_stats(self, session_id):
        """Получить статистику сессии"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT COUNT(*)                                            as total_messages,
                                  SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END)      as user_messages,
                                  SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages,
                                  AVG(response_time)                                  as avg_response_time
                           FROM chat_messages
                           WHERE session_id = ?
                           ''', (session_id,))

            row = cursor.fetchone()
            conn.close()

            return {
                'total_messages': row[0] or 0,
                'user_messages': row[1] or 0,
                'assistant_messages': row[2] or 0,
                'avg_response_time': round(row[3] or 0, 2)
            }


class UserDatabase:
    def __init__(self, db_path="chat_history.db"):
        self.db_path = db_path
        self.lock = Lock()
        self.init_user_table()

    def init_user_table(self):
        """Инициализация таблицы пользователей"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               id            INTEGER PRIMARY KEY AUTOINCREMENT,
                               username      TEXT UNIQUE NOT NULL,
                               password_hash TEXT        NOT NULL,
                               created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                               last_login    DATETIME
                           )
                           ''')

            # Создаем таблицу для сессий чата
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS chat_sessions
                           (
                               id         INTEGER PRIMARY KEY AUTOINCREMENT,
                               user_id    INTEGER     NOT NULL,
                               session_id TEXT UNIQUE NOT NULL,
                               title      TEXT     DEFAULT 'Новый чат',
                               created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                               updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                               FOREIGN KEY (user_id) REFERENCES users (id)
                           )
                           ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_session ON chat_messages(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user ON chat_messages(user_id)')

            # Проверяем, существует ли колонка user_id в chat_messages
            cursor.execute("PRAGMA table_info(chat_messages)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'user_id' not in columns:
                cursor.execute('''
                               ALTER TABLE chat_messages
                                   ADD COLUMN user_id INTEGER DEFAULT NULL
                               ''')
                print("✅ Добавлена колонка user_id в таблицу chat_messages")

            conn.commit()
            conn.close()

    def delete_session(self, session_id):
        """Удаление сессии и всех её сообщений"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                # Сначала удаляем все сообщения сессии
                cursor.execute('DELETE FROM chat_messages WHERE session_id = ?', (session_id,))

                # Затем удаляем саму сессию
                cursor.execute('DELETE FROM chat_sessions WHERE session_id = ?', (session_id,))

                conn.commit()
                print(f"✅ Сессия {session_id} и все её сообщения удалены")

            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    def verify_user(self, username, password):
        """Проверка пользователя"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
            result = cursor.fetchone()

            if result:
                user_id, password_hash = result

                # Проверяем, что хеш пароля не пустой
                if password_hash and password_hash.strip():
                    try:
                        # Проверяем если это bcrypt хеш
                        if password_hash.startswith('$2b$') or password_hash.startswith('$2a$'):
                            # Используем bcrypt для проверки
                            if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                                # Обновляем время последнего входа
                                cursor.execute('UPDATE users SET last_login = ? WHERE id = ?',
                                               (datetime.now(), user_id))
                                conn.commit()
                                conn.close()
                                return user_id
                        else:
                            # Используем Werkzeug для проверки
                            if check_password_hash(password_hash, password):
                                # Обновляем время последнего входа
                                cursor.execute('UPDATE users SET last_login = ? WHERE id = ?',
                                               (datetime.now(), user_id))
                                conn.commit()
                                conn.close()
                                return user_id
                    except Exception as e:
                        print(f"❌ Ошибка проверки пароля для пользователя {username}: {str(e)}")
                else:
                    print(f"❌ Пользователь {username} имеет пустой хеш пароля")

            conn.close()
            return None

    def create_session(self, user_id, title="Новый чат"):
        """Создание новой сессии чата"""
        session_id = f"session_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           INSERT INTO chat_sessions (user_id, session_id, title)
                           VALUES (?, ?, ?)
                           ''', (user_id, session_id, title))

            conn.commit()
            conn.close()

        return session_id

    def get_user_sessions(self, user_id):
        """Получение всех сессий пользователя"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT session_id, title, created_at, updated_at
                           FROM chat_sessions
                           WHERE user_id = ?
                           ORDER BY updated_at DESC
                           ''', (user_id,))

            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    'session_id': row[0],
                    'title': row[1],
                    'created_at': row[2],
                    'updated_at': row[3]
                })

            conn.close()
            return sessions

    def update_session_title(self, session_id, title):
        """Обновление названия сессии"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           UPDATE chat_sessions
                           SET title      = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE session_id = ?
                           ''', (title, session_id))

            conn.commit()
            conn.close()
