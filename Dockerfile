FROM python:3

COPY requirements.txt /
RUN pip install -r requirements.txt

COPY app.py rabbitlistener.py /

CMD gunicorn -w 1 app:app