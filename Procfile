release: python manage.py migrate --noinput
web: gunicorn --config config/gunicorn.conf.py config.wsgi:application
