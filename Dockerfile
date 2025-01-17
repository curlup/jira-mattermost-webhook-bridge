# Use Python 3.9 slim base image
FROM python:3.9-slim

# Set working directory in the container
WORKDIR /app

# Copy application files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port the app runs on
EXPOSE 5000

# Run the application with Waitress
CMD ["python", "app.py"]