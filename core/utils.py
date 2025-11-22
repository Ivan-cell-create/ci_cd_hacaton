from pathlib import Path
from typing import List, Dict, Optional, Any

def find_env_files(repo_path: Path) -> Dict[str, Any] :
    """
        Находит файлы, которые согласно безопасности не должны быть в репозитории
        Находит файл env.example
        Парсит файл env.example и возвращает содержимое env.example

    Args:
        repo_path: Корень проекта

    Returns:
            Dict[str, Any]:
            Словарь вида
            `danger` - danger: List[Path] - все файлы, которые нельзя коммитить,
            `example` - example: List[Path] - список найденных .env.example,
            `variables` - variables: Dict[str, str] - готовый словарь
    """
    danger: List[Path] = []
    example_files: List[Path] = []
    variables: Dict[str, Dict[str, str]] = {}
    result: Dict[str, Any] = {}
    # Список опасных шаблонов файлов
    danger_patterns: List[str] = ["*.env", "*.env.*[!example]"]
    # Список шаблонов example файлов
    example_patterns: List[str] = ["*.env.example", "*.env.*.example"]

    for pattern in danger_patterns:
        danger += list(Path(repo_path).rglob(pattern))
    result["danger"] = danger

    for pattern in example_patterns:
        example_files += list(Path(repo_path).rglob(pattern))
    result["example"] = example_files

    for file in example_files:
        variables[file.name] = parse_env_example(file)
    result["variables"] = variables

    return result

def parse_env_example(example_path: Optional[Path]) -> Dict[str, str]:
    """
        Парсит файл env.example

    Args:
        example_path: Путь к файлу env.example

    Returns:
        Словарь вида `Key` - `Value`
    """

    env_vars: Dict[str, str] = {}
    try:
        with open(example_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith("#"):
                    continue

                # Разделяем по первому знаку "="
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    except FileNotFoundError:
        print(f"Error: File {example_path} not found.")
    except Exception as e:
        print(f"Error reading file: {e}")

    return env_vars

def clean_repo_name(path: Path):
    """
        Рекурсивно удаляет директорию со всем содержимым

        Args:
            path: Путь до директории
    """

    if path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        # Рекурсивно удаляем все содержимое
        for item in path.iterdir():
            clean_repo_name(item)
        # Удаляем саму директорию
        path.rmdir()

def get_repo_name(source: str | Path) -> str:
    """
        Возвращает название репозитория

        Args:
            source: Источник репозитория

        Returns:
            Название репозитория
    """

    if isinstance(source, Path):
        return source.name.replace(".git", "") if source.name else "unknown-repo"
    elif isinstance(source, str):
        src = source.replace("\\", "/")
        if src.startswith("git@") or src.startswith("http") or src.startswith("https"):
            return src.replace(".git", "").split(':')[-1].split('/')[-1]
        elif '/' in src or ".git" in src:
            return src.replace(".git", "").split('/')[-1]
        else:
            return "unknown-repo"
    else:
        return "unknown-repo"