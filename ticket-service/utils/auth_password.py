"""Password hashing and verification using Argon2 (argon2-cffi)"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError


# Единственный инстанс хэшера с безопасными параметрами по умолчанию:
# time_cost=3 (итерации), memory_cost=65536 (64MB), parallelism=4
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)


def hash_password(password: str) -> str:
    """
    Хэширует пароль с помощью Argon2id.

    Соль генерируется автоматически при каждом вызове —
    два вызова с одним паролем дадут разные хэши.

    Args:
        password: Пароль в открытом виде.

    Returns:
        Строка-хэш в формате Argon2 (содержит параметры и соль).

    Raises:
        ValueError: Если пароль пустой.
    """
    if not password:
        raise ValueError("Password must not be empty")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Проверяет пароль против сохранённого Argon2-хэша.

    Args:
        password:      Пароль в открытом виде для проверки.
        password_hash: Хэш из базы данных.

    Returns:
        True если пароль верный, False если нет.

    Raises:
        ValueError: Если пароль или хэш пустые.
    """
    if not password:
        raise ValueError("Password must not be empty")
    if not password_hash:
        raise ValueError("Password hash must not be empty")

    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """
    Проверяет, нужно ли перехэшировать пароль
    (например, если параметры хэшера были обновлены).

    Вызывать после успешного verify_password — если True,
    обновить хэш в БД.
    """
    return _hasher.check_needs_rehash(password_hash)
