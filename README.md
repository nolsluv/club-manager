# Club Manager

A Django web app for managing a school club — members, events, and finances.

## Tech Stack

Python / Django, SQLite (dev) → PostgreSQL (prod), django-environ for config.

## Getting Started

```
git clone https://github.com/your-username/club-manager.git
cd club-manager

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
```

Create a `.env` file at the project root with:
```
DJANGO_SECRET_KEY=your-generated-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```
Generate a key with:
```
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Then:
```
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
App: `http://127.0.0.1:8000/` — Admin: `http://127.0.0.1:8000/admin/`

## Project Structure

```
club-manager/
├── club_manager/    # Settings, URLs
├── members/         # Member model, directory
├── events/          # Event model, RSVPs
├── finances/        # Dues, expenses, balances
├── manage.py
└── requirements.txt
```

## Contributing

We follow **GitHub Flow** — branch, PR, review, merge. See [`WORKFLOW.md`](./WORKFLOW.md).
