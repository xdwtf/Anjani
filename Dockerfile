# Set base image (host OS)
FROM python:3.9-slim-bullseye

# Set the working directory in the container
WORKDIR /anjani/

# Install all required packages
RUN apt-get -qq update && apt-get -qq upgrade -y
RUN apt-get -qq install -y --no-install-recommends \
    curl \
    git \
    gnupg2

# copy pyproject.toml and poetry.lock for layer caching
COPY pyproject.toml poetry.lock ./

# ignore pip root user warning
ENV PIP_ROOT_USER_ACTION=ignore

RUN pip install --upgrade pip
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/install-poetry.py | python -

# Add poetry environment
ENV PATH="${PATH}:/root/.local/bin:$PATH"

RUN poetry config virtualenvs.create false
RUN poetry install --no-root --only main -E uvloop

# copy the rest of files
COPY . .

# Expose port 8080 for the Flask app
EXPOSE 8080

# Start the bot
CMD python -m anjani & flask run --host=0.0.0.0 --port=8080
