FROM python:3.12

COPY requirements.txt /
RUN pip install -r requirements.txt

COPY app.py rabbitlistener.py cacher.py /

EXPOSE 8000
CMD gunicorn -w 1 -b 0.0.0.0:8000 app:app