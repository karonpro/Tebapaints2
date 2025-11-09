# gunicorn.conf.py
bind = "0.0.0.0:8080"
workers = 2
timeout = 120
keepalive = 5
worker_class = "sync"
preload_app = True
