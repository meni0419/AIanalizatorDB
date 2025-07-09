
import os
import pymysql
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
from contextlib import contextmanager
import time

load_dotenv()

@contextmanager
def get_db_connection():
    """
    Создает SSH-туннель и подключается к БД с использованием pymysql.
    """
    ssh_host = os.getenv('SSH_HOST')
    ssh_port = int(os.getenv('SSH_PORT'))
    ssh_user = os.getenv('SSH_USER')
    ssh_key = os.getenv('SSH_KEY_PATH')

    db_host = os.getenv('DB_HOST')
    db_port = int(os.getenv('DB_PORT'))
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    print(f"Создаем SSH-туннель: {ssh_user}@{ssh_host}:{ssh_port}")

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_pkey=ssh_key,
        remote_bind_address=(db_host, db_port)
    )

    print("Запускаем SSH-туннель...")
    tunnel.start()
    connection = None

    try:
        print(f"Туннель запущен, локальный порт: {tunnel.local_bind_port}")

        # Даем время туннелю стабилизироваться
        time.sleep(2)

        print("Подключаемся к базе данных через pymysql...")

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

        print("Подключение к БД установлено!")
        yield connection

    except Exception as error:
        print(f"Ошибка при подключении: {error}")
        raise Exception(f"Failed to connect to database: {error}")
    finally:
        print("Закрываем соединения...")
        if connection:
            connection.close()
            print("Соединение с БД закрыто")
        tunnel.stop()
        print("SSH-туннель остановлен")