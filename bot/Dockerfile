FROM python:3.12-slim

WORKDIR /app/bot

# Install dependencies first (cached layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot code
COPY . .

# Default command: run the bot (overridden in docker-compose for the API service)
CMD ["python", "bot.py"]
