#!/usr/bin/env python3
import sqlite3
from werkzeug.security import generate_password_hash


def update_passwords():
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()

    # Обновляем пароли для существующих пользователей
    passwords = [
        ('mm', 'admin123'),
        ('aalityagin', 'user123'),
    ]

    for username, password in passwords:
        hash_password = generate_password_hash(password)
        cursor.execute(
            'UPDATE users SET password_hash = ? WHERE username = ?',
            (hash_password, username)
        )
        print(f"✅ Обновлен пароль для {username}: {password}")

    # Создаем тестового пользователя
    test_hash = generate_password_hash('test123')
    try:
        cursor.execute(
            'INSERT INTO users (username, password_hash) VALUES (?, ?)',
            ('test', test_hash)
        )
        print("✅ Создан тестовый пользователь: test / test123")
    except sqlite3.IntegrityError:
        cursor.execute(
            'UPDATE users SET password_hash = ? WHERE username = ?',
            (test_hash, 'test')
        )
        print("✅ Обновлен пароль для test: test123")

    conn.commit()
    conn.close()
    print("✅ Все пароли обновлены!")


if __name__ == "__main__":
    update_passwords()