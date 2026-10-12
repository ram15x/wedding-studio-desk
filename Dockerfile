FROM python:3.12-slim
WORKDIR /app
COPY . /app
EXPOSE 8787
CMD ["python", "app.py"]
