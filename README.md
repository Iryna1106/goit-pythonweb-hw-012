# Contacts REST API (goit-pythonweb-hw-012)

REST API для зберігання та управління контактами з повним фінальним стеком домашніх робіт:
**JWT аутентифікація** з парою `access_token`/`refresh_token`, верифікація email,
**скидання пароля**, **ролі користувачів** (`user`/`admin`), **кешування поточного
користувача в Redis**, обмеження швидкості, CORS, завантаження аватарів через
Cloudinary, документація **Sphinx**, тести **pytest** з покриттям ≥ 75%.

Стек: **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL**, **Redis**, **Alembic**,
**Pydantic v2**, **passlib[bcrypt]**, **python-jose**, **fastapi-mail**,
**slowapi**, **cloudinary**, **Sphinx**, **pytest** + **pytest-cov**.

## Що нового у hw-012

| Функція | Де реалізовано |
|---|---|
| Ролі `user` / `admin` (тільки адмін може оновити аватар) | `src/database/models.py`, `src/services/auth.py` (`require_admin`), `src/api/users.py` |
| Кешування поточного користувача у Redis | `src/services/cache.py`, `get_current_user` у `src/services/auth.py` |
| Скидання пароля поштою | `POST /api/auth/reset-password`, `POST /api/auth/reset-password/confirm` |
| `access_token` + `refresh_token` | `POST /api/auth/login`, `POST /api/auth/refresh` |
| Sphinx-документація | `docs/` (`make html`) |
| Тести (модульні + інтеграційні) | `tests/`, `pytest --cov=src --cov=main` (≥ 92%) |
| Redis у `docker-compose.yml` | `docker-compose.yml` |

## Швидкий старт

### 1. Створити `.env`

```bash
cp .env.example .env
```

Заповніть значення для `JWT_SECRET_KEY`, пошти (`MAIL_*`), Cloudinary (`CLOUDINARY_*`)
та Redis (`REDIS_URL`).

### 2. Запустити PostgreSQL та Redis

```bash
docker compose up -d
```

### 3. Встановити залежності

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

### 4. Застосувати міграції

```bash
alembic upgrade head
```

### 5. Запустити застосунок

```bash
python main.py
# або
uvicorn main:app --reload
```

Swagger UI: <http://localhost:8000/docs>

## Тести та покриття

```bash
pytest --cov=src --cov=main --cov-report=term-missing
```

Поточне покриття: **≥ 92%** (вимога — мінімум 75%).

## Документація (Sphinx)

```bash
cd docs
make html
# або без Make:
sphinx-build -b html source build/html
```

Згенеровані сторінки: `docs/build/html/index.html`.

## Ендпоінти

### Аутентифікація (`/api/auth`)

| Метод | Шлях | Опис |
|---|---|---|
| POST | `/api/auth/register` | Реєстрація. **201** — створено; **409** — email/username зайнятий |
| POST | `/api/auth/login` | OAuth2 password form (`username`, `password`) → `access_token` + `refresh_token`. **401** при невірних кредах або непідтвердженому email |
| POST | `/api/auth/refresh` | Отримати нову пару токенів за валідним `refresh_token` |
| GET | `/api/auth/confirmed_email/{token}` | Підтвердження email за токеном |
| POST | `/api/auth/request_email` | Повторно запросити лист підтвердження |
| POST | `/api/auth/reset-password` | Запит на скидання пароля (надсилає лист) |
| POST | `/api/auth/reset-password/confirm` | Встановити новий пароль за токеном з листа |

### Користувачі (`/api/users`)

| Метод | Шлях | Опис |
|---|---|---|
| GET | `/api/users/me` | Профіль поточного користувача (rate limit 5/min) |
| PATCH | `/api/users/avatar` | Оновити аватар (multipart `file`). **Доступно тільки для ролі `admin`** |

### Контакти (`/api/contacts`) — потребує `Authorization: Bearer <access_token>`

| Метод | Шлях | Опис |
|---|---|---|
| GET | `/api/contacts/` | Список власних контактів + фільтри `first_name`, `last_name`, `email`, `skip`, `limit` |
| GET | `/api/contacts/upcoming-birthdays` | Контакти з ДН на найближчі `days` днів (за замовчуванням 7) |
| GET | `/api/contacts/{id}` | Отримати власний контакт за id |
| POST | `/api/contacts/` | Створити контакт (201) |
| PUT | `/api/contacts/{id}` | Оновити власний контакт |
| DELETE | `/api/contacts/{id}` | Видалити власний контакт |

## Конфіденційні дані

Усі секрети живуть лише в `.env` (вже у `.gitignore`). У коді немає захардкоджених
кредів — `pydantic-settings` зчитує їх з оточення.

## Структура проєкту

```
goit-pythonweb-hw-012/
├── main.py
├── docker-compose.yml          # PostgreSQL + Redis
├── alembic.ini
├── requirements.txt
├── pytest.ini
├── .env.example
├── docs/                       # Sphinx
│   ├── Makefile
│   └── source/{conf.py, *.rst}
├── migrations/versions/
│   ├── 0001_create_contacts_table.py
│   ├── 0002_add_users_and_link_contacts.py
│   └── 0003_add_user_role.py
├── src/
│   ├── api/{auth.py, users.py, contacts.py}
│   ├── conf/config.py
│   ├── database/{db.py, models.py}
│   ├── repository/{users.py, contacts.py}
│   ├── schemas/{users.py, contacts.py}
│   └── services/{auth.py, cache.py, email.py, upload_file.py, templates/}
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_repository_users.py
    │   ├── test_repository_contacts.py
    │   ├── test_services_auth.py
    │   └── test_services_cache.py
    └── integration/
        ├── conftest.py
        ├── test_auth_routes.py
        ├── test_users_routes.py
        └── test_contacts_routes.py
```
