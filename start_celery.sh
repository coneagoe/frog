#!/bin/bash

celery -A celery_app worker --loglevel=info &

celery -A celery_app beat --loglevel=info
