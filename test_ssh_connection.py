import os
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
import paramiko

load_dotenv()


def test_ssh_key():
    """Тестирует SSH-ключ"""
    try:
        ssh_key_path = os.getenv('SSH_KEY_PATH')
        print(f"Проверяем SSH-ключ: {ssh_key_path}")

        # Проверяем существование файла
        if not os.path.exists(ssh_key_path):
            print(f"ОШИБКА: SSH-ключ не найден по пути {ssh_key_path}")
            return False

        # Проверяем права доступа
        stat_info = os.stat(ssh_key_path)
        print(f"Права доступа к ключу: {oct(stat_info.st_mode)[-3:]}")

        # Пробуем загрузить ключ
        key = paramiko.RSAKey.from_private_key_file(ssh_key_path)
        print("SSH-ключ загружен успешно")
        return True

    except Exception as e:
        print(f"Ошибка при проверке SSH-ключа: {e}")
        return False


def test_ssh_tunnel():
    """Тестирует создание SSH-туннеля"""
    try:
        ssh_host = os.getenv('SSH_HOST')
        ssh_port = int(os.getenv('SSH_PORT'))
        ssh_user = os.getenv('SSH_USER')
        ssh_key = os.getenv('SSH_KEY_PATH')

        print(f"Тестируем SSH-туннель: {ssh_user}@{ssh_host}:{ssh_port}")

        tunnel = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_user,
            ssh_pkey=ssh_key,
            remote_bind_address=('127.0.0.1', 3306),
            # Убираем неподдерживаемые параметры
            allow_agent=False,
            host_pkey_directories=[]
        )

        print("Запускаем туннель...")
        tunnel.start()
        print(f"Туннель запущен! Локальный порт: {tunnel.local_bind_port}")

        # Проверяем активность туннеля
        if tunnel.is_active:
            print("Туннель активен!")
            tunnel.stop()
            return True
        else:
            print("Туннель не активен!")
            return False

    except Exception as e:
        print(f"Ошибка при создании туннеля: {e}")
        return False


if __name__ == "__main__":
    print("=== Тестирование SSH-подключения ===")

    if test_ssh_key():
        print("\n=== Тестирование SSH-туннеля ===")
        test_ssh_tunnel()
    else:
        print("Не удалось проверить SSH-ключ")