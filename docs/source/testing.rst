Тестування
==========

Запуск
------

.. code-block:: bash

   pytest

``pytest.ini`` уже містить:

* ``--cov=src --cov=main`` — вимірюється і код застосунку, і ``main.py``.
* ``--cov-fail-under=75`` — pytest падає якщо покриття опускається
  нижче 75%.
* ``--cov-report=term-missing`` — рядки без покриття у консолі.
* ``--cov-report=html`` — HTML-звіт у ``htmlcov/index.html``.
* ``--cov-report=xml`` — ``coverage.xml`` для CI / SonarQube.

Структура тестів
----------------

* ``tests/unit/`` — модульні тести з мок-сесіями SQLAlchemy:
  ``test_repository_users.py``, ``test_repository_contacts.py``,
  ``test_services_auth.py``, ``test_services_cache.py``.
* ``tests/integration/`` — повний прогін через ``TestClient``,
  in-memory SQLite:
  ``test_auth_routes.py``, ``test_users_routes.py``,
  ``test_contacts_routes.py``, ``test_cache_integration.py``,
  ``test_scenarios.py``.

Що покривають інтеграційні сценарії
-----------------------------------

* Повний user journey — register → confirm → login → refresh → CRUD →
  delete (``test_full_user_journey``).
* Повний flow скидання пароля з перевіркою single-use токену
  (``test_password_reset_full_flow``, ``test_reset_token_is_single_use``).
* Cross-tenant ізоляція — користувачі не бачать чужих контактів
  (``test_users_cannot_see_each_others_contacts``).
* Адмін-ендпойнти — список користувачів, зміна ролі, захист від
  self-demotion (``test_admin_can_*``).
* Кешування — друге звернення до ``/api/users/me`` обслуговується
  з Redis і не торкається БД
  (``test_me_reads_from_cache_on_second_call``).
* Edge-кейси refresh-токенів (``test_refresh_for_deleted_user_returns_401``).

Поточне покриття
----------------

.. code-block:: text

   TOTAL  91.4%   (gate: 75%)

Артефакти ``htmlcov/`` та ``coverage.xml`` створюються при кожному
запуску ``pytest`` локально та в CI.
