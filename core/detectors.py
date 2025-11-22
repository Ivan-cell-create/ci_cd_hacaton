from pathlib import Path
from typing import Dict, Any, Callable, Tuple

Detector = Callable[[Path], bool]
StackInfo = Tuple[str, str, Detector]  # (stack_name, template_name detector_func)


def _has_file(repo: Path, pattern: str) -> bool:
    """
    Проверяет, есть ли в репозитории хотя бы один файл, подходящий под glob-шаблон.
    Поиск рекурсивный - проходит по всем подпапкам.

    Используется, когда файл может лежать в любой директории проекта
    (requirements-dev.txt, *.gradle.kts, Dockerfile в подпапке и т.п.).

    Args:
        repo (Path): корневая директория репозитория
        pattern (str): glob-шаблон для поиска
            - "requirements*.txt" - найдёт requirements.txt, requirements-dev.txt и др.
            - "*.gradle.kts" - найдёт все Kotlin Gradle-скрипты в любом месте
            - "Dockerfile"     - точное имя тоже поддерживается

    Returns:
        bool: True - если найден хотя бы один файл по шаблону, иначе False

    Examples:
        >>> _has_file(repo, "requirements*.txt")    # - True для pip-проектов
        >>> _has_file(repo, "*.csproj")             # - True для .NET
    """
    return any(repo.rglob(pattern))


def _file_exists(repo: Path, filename: str) -> bool:
    """
    Проверяет наличие файла с точным именем строго в корне репозитория.

    Используется для ключевых манифестов проекта, которые по стандарту должны лежать в корне:
        package.json, pyproject.toml, go.mod, Cargo.toml, pom.xml и т.д.
    Если файл лежит в подпапке - это обычно монорепо или ошибка - игнорируем.

    Args:
        repo (Path): корневая директория репозитория
        filename (str): точное имя файла (например: "package.json", "go.mod")

    Returns:
        bool: True - если файл существует в корне, иначе False

    Examples:
        >>> _file_exists(repo, "package.json")   # - Node.js проект
        >>> _file_exists(repo, "Cargo.toml")     # - Rust проект на Rust
    """
    return repo.joinpath(filename).is_file()


def _file_contains(repo: Path, filename: str, substring: str) -> bool:
    """
    Безопасно читает файл из корня репозитория и проверяет,
    содержится ли в нём указанная подстрока (нечувствительно к регистру).

    Основное применение - определение менеджера зависимостей в pyproject.toml:
        [tool.poetry], [tool.uv], [tool.pdm] и т.п.

    Защита от:
        - битых кодировок (errors="ignore")
        - отсутствия файла
        - ошибок доступа / повреждений

    Args:
        repo (Path): корневая директория репозитория
        filename (str): имя файла в корне (например: "pyproject.toml")
        substring (str): подстрока для поиска (например: "[tool.poetry]")

    Returns:
        bool: True - если подстрока найдена в содержимом файла

    Examples:
        >>> _file_contains(repo, "pyproject.toml", "[tool.poetry]")  # - Poetry
        >>> _file_contains(repo, "pyproject.toml", "[tool.uv]")      # - uv
    """
    path = repo.joinpath(filename)
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return substring.lower() in content.lower()
    except Exception:
        return False


def _pyproject_has_tool(repo: Path, tool_name: str) -> bool:
    """
    Проверяет, используется ли конкретный инструмент в pyproject.toml через секцию [tool.<tool_name>].

    Это основной способ определить современный менеджер зависимостей в Python-проектах 2023–2026 годов:
        - [tool.poetry]  - Poetry
        - [tool.uv]      - uv (самый быстрый в 2025+)
        - [tool.pdm]     - PDM
        - [tool.hatch]   - Hatch
        - [tool.flit]    - Flit

    Функция комбинирует два надёжных проверки:
        1. Файл pyproject.toml есть в корне репозитория
        2. Внутри файла есть нужная секция TOML (нечувствительно к регистру и пробелам)

    Args:
        repo (Path): корневая директория репозитория
        tool_name (str): имя инструмента в нижнем регистре, например:
            "poetry", "uv", "pdm", "hatch", "ruff", "black"

    Returns:
        bool: True - если pyproject.toml существует и содержит секцию [tool.<tool_name>]

    Examples:
        >>> _pyproject_has_tool(repo, "poetry")   # - True для Poetry-проектов
        >>> _pyproject_has_tool(repo, "uv")       # - True для проектов на uv
        >>> _pyproject_has_tool(repo, "pdm")      # - True для PDM
        >>> _pyproject_has_tool(repo, "django")    # - False (нет такой секции)
    """
    return _file_exists(repo, "pyproject.toml") and _file_contains(
        repo, "pyproject.toml", f"[tool.{tool_name}]"
    )

# Детекторы стеков
def _detect_docker(repo: Path) -> bool:
    """Docker - максимальный приоритет, перекрывает всё"""
    return _has_file(repo, "Dockerfile") or _has_file(repo, "dockerfile")


def _detect_node_npm(repo: Path) -> bool:
    """Node.js + npm - только если нет lock-файлов от yarn/pnpm/bun"""
    return _file_exists(repo, "package.json") and not (
        _file_exists(repo, "yarn.lock") or
        _file_exists(repo, "pnpm-lock.yaml") or
        _file_exists(repo, "bun.lockb")
    )


def _detect_node_yarn(repo: Path) -> bool:
    """Node.js + Yarn"""
    return _file_exists(repo, "yarn.lock")


def _detect_node_pnpm(repo: Path) -> bool:
    """Node.js + pnpm"""
    return _file_exists(repo, "pnpm-lock.yaml") or _file_exists(repo, "pnpm-workspace.yaml")


def _detect_node_bun(repo: Path) -> bool:
    """Node.js + Bun (самый быстрый в 2025–2026)"""
    return _file_exists(repo, "bun.lockb")


def _detect_deno(repo: Path) -> bool:
    """Deno"""
    return _has_file(repo, "deno.json*") or _has_file(repo, "import_map.json")


def _detect_python_uv(repo: Path) -> bool:
    """Python + uv - новый лидер 2025–2026"""
    return _pyproject_has_tool(repo, "uv")


def _detect_python_pdm(repo: Path) -> bool:
    """Python + PDM"""
    return _pyproject_has_tool(repo, "pdm")


def _detect_python_poetry(repo: Path) -> bool:
    """Python + Poetry"""
    return _pyproject_has_tool(repo, "poetry")


def _detect_python_pipenv(repo: Path) -> bool:
    """Python + Pipenv"""
    return _file_exists(repo, "Pipfile") or _file_exists(repo, "Pipfile.lock")


def _detect_python_pip(repo: Path) -> bool:
    """Классический Python (pip + requirements*.txt / setup.py)"""
    return (
        _has_file(repo, "requirements*.txt") or
        _file_exists(repo, "setup.py") or
        _file_exists(repo, "setup.cfg")
    )


def _detect_go(repo: Path) -> bool:
    """Go"""
    return _file_exists(repo, "go.mod")


def _detect_rust(repo: Path) -> bool:
    """Rust + Cargo"""
    return _file_exists(repo, "Cargo.toml")


def _detect_java_maven(repo: Path) -> bool:
    """Java/Kotlin + Maven"""
    return _file_exists(repo, "pom.xml")


def _detect_java_gradle(repo: Path) -> bool:
    """Java/Kotlin + Gradle (включая Kotlin DSL)"""
    return (
        _has_file(repo, "*.gradle") or
        _has_file(repo, "*.gradle.kts") or
        _file_exists(repo, "gradlew") or
        _file_exists(repo, "settings.gradle.kts")
    )


def _detect_dotnet(repo: Path) -> bool:
    """.NET (C#/F#)"""
    return _has_file(repo, "*.csproj") or _has_file(repo, "*.fsproj")


def _detect_php_composer(repo: Path) -> bool:
    """PHP + Composer"""
    return _file_exists(repo, "composer.json")


def _detect_elixir(repo: Path) -> bool:
    """Elixir + Mix"""
    return _file_exists(repo, "mix.exs")


def _detect_ruby(repo: Path) -> bool:
    """Ruby + Bundler"""
    return _file_exists(repo, "Gemfile")


def _detect_flutter(repo: Path) -> bool:
    """Flutter / Dart"""
    return _file_exists(repo, "pubspec.yaml")


STACK_PRIORITY: list[StackInfo] = [
    ("docker",          "docker.yml.j2",          _detect_docker),

    ("node-bun",        "node-bun.yml.j2",       _detect_node_bun),
    ("node-pnpm",       "node-pnpm.yml.j2",       _detect_node_pnpm),
    ("node-yarn",       "node-yarn.yml.j2",       _detect_node_yarn),
    ("node-npm",        "node-npm.yml.j2",        _detect_node_npm),
    ("deno",            "deno.yml.j2",            _detect_deno),

    ("python-uv",       "python-uv.yml.j2",      _detect_python_uv),
    ("python-pdm",      "python-pdm.yml.j2",      _detect_python_pdm),
    ("python-poetry",   "python-poetry.yml.j2",   _detect_python_poetry),
    ("python-pipenv",   "python-pipenv.yml.j2",   _detect_python_pipenv),
    ("python-pip",      "python-pip.yml.j2",      _detect_python_pip),

    ("elixir",          "elixir.yml.j2",          _detect_elixir),
    ("ruby",            "ruby.yml.j2",            _detect_ruby),
    ("flutter",         "flutter.yml.j2",         _detect_flutter),

    ("java-maven",      "java-maven.yml.j2",      _detect_java_maven),
    ("java-gradle",     "java-gradle.yml.j2",     _detect_java_gradle),
    ("dotnet",          "dotnet.yml.j2",          _detect_dotnet),

    ("go",              "go.yml.j2",              _detect_go),
    ("rust",            "rust.yml.j2",            _detect_rust),
    ("php-composer",    "php-composer.yml.j2",    _detect_php_composer),
]


def _build_context(repo: Path, stack: str) -> Dict[str, Any]:
    """
    Формирует контекст для Jinja2-шаблона - словарь с командами сборки, тестирования и метаданными,
    специфичными для определённого технологического стека.

    Этот словарь потом подставляется в .j2-шаблоны GitHub Actions и генерирует готовый workflow.

    Общие поля для всех стеков:
        - project_name  - имя проекта в нижнем регистре, пригодное для Docker-тегов и артефактов
        - has_docker    - есть ли Dockerfile (нужно для кэширования/публикации образа)
        - docker_tag      - тег образа по умолчанию (используется в docker/metadata-action)
        - install_cmd   - команда установки зависимостей
        - build_cmd     - команда сборки (если есть)
        - test_cmd      - команда запуска тестов (если есть)
        - artifact_path - путь к артефакту (jar, wheel, бинарник и т.д.)

    Поддерживаемые стеки и их команды актуальны на 2025–2026 год.

    Args:
        repo (Path): путь к корню репозитория
        stack (str): идентификатор стека, например: "python-poetry", "node-bun", "go"

    Returns:
        Dict[str, Any]: контекст для рендеринга GitHub Actions workflow через Jinja2

    Examples:
        >>> _build_context(repo, "python-uv")
        {
            'project_name': 'my-api',
            'has_docker': False,
            'docker_tag': 'my-api:latest',
            'install_cmd': 'uv sync --frozen',
            'test_cmd': 'uv run pytest',
            'build_cmd': 'uv build',
            'artifact_path': None
        }
    """
    ctx: Dict[str, Any] = {
        "project_name": repo.name.lower().replace(" ", "-").replace("_", "-"),
        "has_docker": _detect_docker(repo),
        "docker_tag": f"{repo.name.lower()}:latest",
        "install_cmd": None,
        "build_cmd": None,
        "test_cmd": None,
        "artifact_path": None,
    }

    match stack:
        case "docker":
            ctx["build_cmd"] = "docker build -t ${{ steps.meta.outputs.tags }} ."

        case "node-npm":
            ctx["install_cmd"] = "npm ci --prefer-offline"
            pkg_content = (repo / "package.json").read_text(encoding="utf-8", errors="ignore")
            ctx["build_cmd"] = "npm run build" if '"build"' in pkg_content else None
            ctx["test_cmd"] = "npm test" if '"test"' in pkg_content else None

        case "node-yarn":
            ctx["install_cmd"] = "yarn install --frozen-lockfile"
        case "node-pnpm":
            ctx["install_cmd"] = "pnpm i --frozen-lockfile"
        case "node-bun":
            ctx["install_cmd"] = "bun install --frozen-lockfile"

        case "deno":
            ctx["install_cmd"] = "deno cache main.ts"
            ctx["test_cmd"] = "deno test"

        case "python-uv":
            ctx["install_cmd"] = "uv sync --frozen"
            ctx["test_cmd"] = "uv run pytest" if _has_file(repo, "*test*.py") or _has_file(repo, "tests/") else None
            ctx["build_cmd"] = "uv build" if _pyproject_has_tool(repo, "uv") else None

        case "python-pdm":
            ctx["install_cmd"] = "pdm sync --no-editable"
            ctx["test_cmd"] = "pdm run pytest"

        case "python-poetry":
            ctx["install_cmd"] = "poetry install --no-interaction --no-root"
            ctx["build_cmd"] = "poetry build"
            ctx["test_cmd"] = "poetry run pytest"

        case "python-pipenv":
            ctx["install_cmd"] = "pipenv install --deploy --ignore-pipfile"

        case "python-pip":
            ctx["install_cmd"] = "pip install -r requirements.txt"

        case "go":
            ctx["install_cmd"] = "go mod download"
            ctx["build_cmd"] = "go build -o app ."
            ctx["test_cmd"] = "go test ./..."

        case "rust":
            ctx["build_cmd"] = "cargo build --release"
            ctx["test_cmd"] = "cargo test"

        case "dotnet":
            ctx["install_cmd"] = "dotnet restore"
            ctx["build_cmd"] = "dotnet publish -c Release -o out"
            ctx["artifact_path"] = "out"

        case "php-composer":
            ctx["install_cmd"] = "composer install --no-dev --optimize-autoloader"

        case "elixir":
            ctx["install_cmd"] = "mix deps.get"
            ctx["test_cmd"] = "mix test"

        case "ruby":
            ctx["install_cmd"] = "bundle install --frozen"

        case "flutter":
            ctx["install_cmd"] = "flutter pub get"
            ctx["build_cmd"] = "flutter build apk --release"

    return ctx


def detect_stack(repo_path: Path) -> Dict[str, Any]:
    """
    Основная функция детектора: анализирует репозиторий и определяет его технологический стек.

    Проходит по списку приоритетов (STACK_PRIORITY) сверху вниз.
    Как только находит подходящий стек - сразу возвращает полные данные для генерации GitHub Actions workflow.
    Dockerfile имеет наивысший приоритет и перекрывает все остальные стеки.

    Возвращает словарь, который напрямую используется для рендеринга Jinja2-шаблона:
        - stack        - идентификатор стека (например: "python-poetry", "node-bun")
        - template     - имя .j2-файла из папки templates/
        - context      - все команды, пути и метаданные для подстановки в шаблон

    Если ничего не подошёл ни один детектор - возвращается безопасный fallback "unknown".

    Args:
        repo_path (Path): абсолютный или относительный путь до корня репозитория
                          (должен существовать и быть директорией)

    Returns:
        Dict[str, Any]: данные для генерации workflow.yml через Jinja2
            {
                "stack": str,
                "template": str,
                "context": {
                    "project_name": str,
                    "has_docker": bool,
                    "docker_tag": str,
                    "install_cmd": str | None,
                    "build_cmd": str | None,
                    "test_cmd": str | None,
                    "artifact_path": str | None,
                    ...
                }
            }

    Raises:
        ValueError: если путь не существует или не является директорией

    Examples:
        >>> detect_stack(Path("/home/user/my-api"))
        {
            'stack': 'python-uv',
            'template': 'python-uv.yml.j2',
            'context': { ... }
        }
    """
    if not repo_path.is_dir():
        raise ValueError(f"Путь {repo_path} не существует или не является директорией")

    for stack_name, template_name, detector in STACK_PRIORITY:
        if detector(repo_path):
            return {
                "stack": stack_name,
                "template": template_name,
                "context": _build_context(repo_path, stack_name),
            }

    # Fallback - репозиторий не опознан
    return {
        "stack": "unknown",
        "template": "unknown.yml.j2",
        "context": {
            "project_name": repo_path.name.lower().replace(" ", "-"),
            "has_docker": _detect_docker(repo_path),
            "docker_tag": f"{repo_path.name.lower()}:latest",
            "install_cmd": None,
            "build_cmd": None,
            "test_cmd": None,
            "artifact_path": None,
        },
    }