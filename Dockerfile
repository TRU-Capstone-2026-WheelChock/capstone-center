FROM python:3.12-slim

WORKDIR /app
COPY . .

CMD ["python", "-c", "print('capstone-center up')"]
