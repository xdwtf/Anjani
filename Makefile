IMAGE_NAME=anjani
CONTAINER_NAME=anjaniBot
VERSION:=$(shell grep -m 1 version pyproject.toml | cut -d '"' -f 2)

.PHONY: help test

help:
	@echo "Userbotindo - Anjani v$(VERSION)"
	@echo ""
	@echo "Makefile commands:"
	@echo "  fetch-origin: Fetch the latest changes from the origin"
	@echo "  build(*-nc): Build the docker image"
	@echo "  run: Run the docker container"
	@echo "  stop: Stop the docker container"
	@echo "  up(*-nc): Update latest changes and restart the docker container"
	@echo "  test: Run the tests"
	@echo "  restart: Restart the docker container"
	@echo "\n* nc = no-cache (optional e.g: make build-nc)"

fetch-origin:
	git pull origin

build: fetch-origin
	docker build . -t $(IMAGE_NAME)

build-nc: fetch-origin
	docker build . -t $(IMAGE_NAME) --no-cache

run:
	@echo "Starting Anjani(v$(VERSION))"
	docker run -d --restart unless-stopped --name $(CONTAINER_NAME) $(IMAGE_NAME)

stop:
	docker container stop $(CONTAINER_NAME) || true
	docker container rm $(CONTAINER_NAME) || true

up: build stop run

up-nc: build-nc stop run

test:
	poetry run pytest -v

restart: stop run

.ONESHELL:
bump:
	@echo "Updating version"
	@echo "Current version: v$(VERSION)"
	NEW_VERSION=$(shell convco version --bump)
	@echo "Bumping version to v$$NEW_VERSION"

	sed -i "s/version = \"$(VERSION)\"/version = \"$$NEW_VERSION\"/g" pyproject.toml > /dev/null; \
	sed -i "s/__version__ = \"$(VERSION)\"/__version__ = \"$$NEW_VERSION\"/g" anjani/__init__.py > /dev/null; \
	git add pyproject.toml anjani/__init__.py > /dev/null

	@echo "Commiting changes"
	git checkout staging > /dev/null
	git commit -m "Bump version to v$$NEW_VERSION"
	git tag -a "v$$NEW_VERSION" -m "Bump version to v$$NEW_VERSION"
	git checkout master
	git merge staging
	git push --atomic origin master staging "v$$NEW_VERSION"

	@echo "Generating changelog"
	convco changelog -m 1 > CHANGELOG.md
	@echo -e "\n### Version Contributor(s)\n" >> CHANGELOG.md
	@echo $(shell git log --pretty=oneline HEAD...v$(VERSION) --format="@%cN" | sort | uniq | sed s/"@GitHub"// | tr '\n' ' ') >> CHANGELOG.md
	@echo "Changelog saved to CHANGELOG.md"

changelog:
	# https://convco.github.io/
	@echo "Generating changelog"
	convco changelog -m 1 > CHANGELOG.md
	@echo -e "\n### Version Contributor(s)\n" >> CHANGELOG.md
	@echo $(shell git log --pretty=oneline HEAD...v$(VERSION) --format="@%cN" | sort | uniq | sed s/"@GitHub"// | tr '\n' ' ') >> CHANGELOG.md
	@echo "Changelog saved to CHANGELOG.md"

requirements:
	poetry export -E all -f requirements.txt -o requirements.txt --without-hashes
