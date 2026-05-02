Auth Flow
=========

Реєстрація і верифікація
------------------------

.. code-block:: text

   POST /api/auth/register   →  201 + UserResponse(confirmed=False)
                                + надсилається лист з email_token
   GET  /api/auth/confirmed_email/{token}  → 200, користувач confirmed=True

Login + видача токенів
----------------------

.. code-block:: text

   POST /api/auth/login   (form: username, password)
   →  200 { access_token, refresh_token, token_type:"bearer" }

* ``access_token`` — scope ``access_token``, TTL ~60 хв
* ``refresh_token`` — scope ``refresh_token``, TTL 7 днів

Усі захищені маршрути читають Bearer access-токен. Залежність
:func:`src.services.auth.get_current_user` валідизує scope, термін дії
та підпис, після чого віддає :class:`src.database.models.User` (з
кешу або з БД).

Refresh
-------

.. code-block:: text

   POST /api/auth/refresh   { refresh_token }
   →  200 { access_token, refresh_token }   # обидва оновлюються

Refresh-токен не може використовуватись як access-токен (різний scope),
а access-токен — навпаки. :func:`src.services.auth.decode_token` суворо
перевіряє ``scope``-claim.

Скидання пароля (single-use)
----------------------------

.. code-block:: text

   POST /api/auth/reset-password         { email }
   →  200 (generic message — не палить, чи email зареєстрований)
   → лист з посиланням ?token=<jwt scope=reset_password jti=<uuid>>

   POST /api/auth/reset-password/confirm { token, new_password }
   →  200 UserResponse — пароль змінено
   → JTI позначено спожитим у Redis на залишок TTL

   повторна спроба з тим же токеном:
   →  400 "Reset token has already been used"

Кешований профіль користувача автоматично інвалідовується після зміни
пароля, так що подальші запити побачать новий хеш.

Ролі: лише адмін
----------------

.. code-block:: text

   PATCH /api/users/avatar     # 403 для звичайного user
   GET   /api/users/           # 403 для звичайного user
   PATCH /api/users/{id}/role  # 403 + захист від self-demotion (400)
