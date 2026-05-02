Contacts REST API
=================

REST API для зберігання та управління контактами на FastAPI 2.0.
Підтримує JWT з парою токенів (access + refresh), верифікацію email,
скидання пароля з одноразовими токенами, ролі користувачів
(``user`` / ``admin``) з адмін-only маршрутами та кешування поточного
користувача в Redis.

Зміст
-----

.. toctree::
   :maxdepth: 2
   :caption: Огляд

   overview
   auth_flow
   testing
   deployment

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
