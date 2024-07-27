# Use the official Python image as a base
FROM python:3.10-slim-bullseye AS base

# Environment variables for Poetry and Python
ENV POETRY_NO_INTERACTION=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_CACHE_DIR='/tmp/poetry_cache' \
    PYTHONDONTWRITEBYTECODE=1

# Install necessary packages and Doppler CLI
RUN apt-get -qq update && \
    apt-get -qq install -y --no-install-recommends curl gcc apt-transport-https ca-certificates gnupg && \
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | tee /etc/apt/sources.list.d/doppler-cli.list && \
    apt-get update && \
    apt-get -y install doppler

# Use the base image to create a builder stage
FROM base AS builder
WORKDIR /app

# Copy the Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Upgrade pip and install Poetry
RUN pip install --upgrade pip && \
    pip install poetry

# Install dependencies using Poetry
RUN poetry install --no-root --only main -E uvloop

# Install git for version control
RUN apt-get -qq install -y --no-install-recommends git

# Use the base image to create the final runner stage
FROM base AS runner
WORKDIR /app

# Set the environment variables for the virtual environment
ENV VENV_PATH=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Copy the virtual environment from the builder stage
COPY --from=builder $VENV_PATH $VENV_PATH

# Copy the application code
COPY . .

# Expose port 8080 for the Flask app
EXPOSE 8080

# Start both bot and Flask app
CMD ["bash", "x.sh"]
