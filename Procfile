release: python manage.py migrate --noinput
web: gunicorn --config config/gunicorn.conf.py config.wsgi:application
worker: celery -A config worker --loglevel=INFO
beat: celery -A config beat --loglevel=INFO
