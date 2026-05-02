Розгортання
===========

Docker Compose (локально)
-------------------------

.. code-block:: bash

   docker compose up --build
   # → http://localhost:8000/docs

Compose піднімає три сервіси: ``postgres``, ``redis``, ``api``.
``DATABASE_URL`` і ``REDIS_URL`` всередині мережі вказують на сервіси
за іменем (``postgres`` / ``redis``).

Render
------

Репозиторій містить :file:`render.yaml` — Render Blueprint, який
провіженить ``Postgres + Key Value (Redis) + Web Service`` з
вашого Docker-образу одним кліком (**New ▸ Blueprint**).

Параметри що Render заповнює автоматично:

* ``DATABASE_URL`` — підв'язується до managed Postgres у тому ж регіоні.
* ``REDIS_URL`` — підв'язується до Key Value.
* ``JWT_SECRET_KEY`` — генерується один раз при першому деплої.

Параметри, що треба заповнити в дашборді (mark ``sync: false``):
``APP_BASE_URL``, ``MAIL_*``, ``CLOUDINARY_*``.

Нормалізація DATABASE_URL
-------------------------

Render та Heroku видають connection string у форматі ``postgres://``,
який SQLAlchemy 2 більше не приймає. Властивість
:attr:`src.conf.config.Settings.database_url_normalized` прозоро
переписує префікс на ``postgresql+psycopg2://``, тож кодова база
працює без змін на будь-якій платформі.

Healthcheck
-----------

* ``GET /healthz`` повертає ``{"status":"ok"}`` — використовується
  Render-ом як ``healthCheckPath``.

Production checklist
--------------------

* ``CORS_ORIGINS`` — конкретний фронтенд URL замість ``*``.
* ``MAIL_*`` — реальні SMTP-реквізити (для Gmail — App Password).
* ``JWT_SECRET_KEY`` — мінімум 32 символи рандомних байт (Render
  генерує сам).
* Включено Redis — інакше кешування і single-use reset токени не
  працюватимуть (застосунок не падає, але деградує до прямого читання
  з БД).
