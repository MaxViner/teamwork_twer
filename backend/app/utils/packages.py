"""Версии установленных пакетов.

package_version() безопасно читает версию библиотеки, а если пакет
не установлен, возвращает строку "unknown". Версии попадают
в наблюдения, чтобы было понятно, чем получен результат.
"""

import importlib.metadata


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
