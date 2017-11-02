run:
	docker-compose up -d

test:
	docker-compose run --rm app python /app/setup.py test

shell:
	docker-compose run --rm app bash
