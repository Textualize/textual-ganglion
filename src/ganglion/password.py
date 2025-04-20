import base64
import hashlib
import secrets

from . import constants

HASH_ITERATIONS = 260000
HASH_ALGORITHM = "pbkdf2_sha256"


def hash_password(password, salt: str | None = None, iterations=HASH_ITERATIONS) -> str:
    """Hash a password.

    Args:
        password: Password.
        salt: Salt or None to make an automatic salt.
        iterations: Number of iterations. Defaults to 260000.

    Returns:
        Hashed password
    """
    password += constants.SECRET
    if salt is None:
        salt = secrets.token_hex(16)
    assert salt and isinstance(salt, str) and "$" not in salt
    assert isinstance(password, str)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
    )
    b64_hash = base64.b64encode(pw_hash).decode("ascii").strip()
    return "{}${}${}${}".format(HASH_ALGORITHM, iterations, salt, b64_hash)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash.

    Args:
        password: Password to check.
        password_hash: Hashed password.

    Returns:
        True if the password matches, otherwise False.
    """

    if (password_hash or "").count("$") != 3:
        return False
    algorithm, iterations, salt, b64_hash = password_hash.split("$", 3)
    int_iterations = int(iterations)
    assert algorithm == HASH_ALGORITHM
    compare_hash = hash_password(password, salt, int_iterations)
    return secrets.compare_digest(password_hash, compare_hash)


if __name__ == "__main__":
    from time import time

    start = time()
    hash = hash_password("foo")
    print(verify_password("foo", hash))
    print(verify_password("bar", hash))
    print(time() - start)
