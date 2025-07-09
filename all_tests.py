import os
import pymysql
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
import time

load_dotenv()


def test_pymysql_connection():
    """Тестирует подключение к MySQL через SSH-туннель с pymysql"""
    ssh_host = os.getenv('SSH_HOST')
    ssh_port = int(os.getenv('SSH_PORT'))
    ssh_user = os.getenv('SSH_USER')
    ssh_key = os.getenv('SSH_KEY_PATH')

    db_host = os.getenv('DB_HOST')
    db_port = int(os.getenv('DB_PORT'))
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    print(f"Создаем SSH-туннель...")

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_pkey=ssh_key,
        remote_bind_address=(db_host, db_port)
    )

    try:
        print("Запускаем SSH-туннель...")
        tunnel.start()
        print(f"SSH-туннель запущен, локальный порт: {tunnel.local_bind_port}")

        # Даем время туннелю стабилизироваться
        time.sleep(2)

        print("Тестируем подключение к MySQL с pymysql...")

        connection = pymysql.connect(
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=10,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

        print("Подключение к MySQL успешно!")

        # Тестируем простой запрос
        cursor = connection.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        print(f"Тестовый запрос выполнен: {result}")

        # Тестируем запрос к реальной таблице
        cursor.execute("SELECT COUNT(*) as count FROM user LIMIT 1")
        result = cursor.fetchone()
        print(f"Количество пользователей: {result}")

        cursor.close()
        connection.close()
        print("Соединение закрыто")

        return True

    except Exception as e:
        print(f"Ошибка при подключении к MySQL: {e}")
        return False
    finally:
        tunnel.stop()
        print("SSH-туннель остановлен")


if __name__ == "__main__":
    test_pymysql_connection()