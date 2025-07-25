import os
import mysql.connector
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv
from contextlib import contextmanager
import time
import socket

load_dotenv()


@contextmanager
def get_db_connection():
    """
    Создает SSH-туннель и подключается к БД.
    Используется как контекстный менеджер (через 'with').
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
    print(f"Используем SSH-ключ: {ssh_key}")
    print(f"Целевая БД: {db_host}:{db_port}")

    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_pkey=ssh_key,
        remote_bind_address=(db_host, db_port)
    )

    print("Запускаем SSH-туннель...")
    start_time = time.time()

    try:
        tunnel.start()
        print(f"SSH-туннель запущен за {time.time() - start_time:.2f} секунд")
        print(f"Локальный порт туннеля: {tunnel.local_bind_port}")

        # Даем время туннелю стабилизироваться
        print("Ожидаем стабилизации туннеля...")
        time.sleep(2)

        # Проверяем доступность порта
        print(f"Проверяем доступность порта {tunnel.local_bind_port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('127.0.0.1', tunnel.local_bind_port))
        sock.close()

        if result != 0:
            raise Exception(f"Порт {tunnel.local_bind_port} недоступен")

        print("Порт доступен, подключаемся к базе данных...")

        connection = None
        connection = mysql.connector.connect(
            host='127.0.0.1',
            port=tunnel.local_bind_port,
            user=db_user,
            password=db_password,
            database=db_name,
            connection_timeout=10,  # Уменьшили таймаут
            autocommit=True,
            use_unicode=True,
            charset='utf8mb4'
        )

        print("Подключение к БД установлено!")
        yield connection

    except mysql.connector.Error as mysql_error:
        print(f"Ошибка MySQL: {mysql_error}")
        raise Exception(f"MySQL connection failed: {mysql_error}")
    except Exception as error:
        print(f"Общая ошибка при подключении: {error}")
        raise Exception(f"Failed to connect to database through SSH tunnel: {error}")
    finally:
        print("Закрываем соединения...")
        if 'connection' in locals() and connection and connection.is_connected():
            connection.close()
            print("Соединение с БД закрыто")
        if tunnel:
            tunnel.stop()
            print("SSH-туннель остановлен")