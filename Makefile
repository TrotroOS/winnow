# Winnow operator targets (host or bind-mount paths matching docker-compose volumes).

BACKUP_RETENTION_DAYS ?= 30
BACKUP_DIR ?= backups
WINNOW_DB_PATH ?= data/winnow.sqlite

.PHONY: backup backup-prune test docker-build docker-up docker-once docker-dry-run

backup:
	@test -f "$(WINNOW_DB_PATH)" || (echo "database missing: $(WINNOW_DB_PATH)" >&2; exit 1)
	@mkdir -p "$(BACKUP_DIR)"
	@dest="$(BACKUP_DIR)/winnow_$$(date -u +%Y%m%dT%H%M%SZ).db"; \
		cp "$(WINNOW_DB_PATH)" "$$dest"; \
		echo "backup: $$dest"
	@$(MAKE) backup-prune

backup-prune:
	@find "$(BACKUP_DIR)" -name 'winnow_*.db' -type f -mtime +$(BACKUP_RETENTION_DAYS) -print -delete 2>/dev/null || true

test:
	python -m pytest -v

docker-build:
	docker compose build

docker-up:
	docker compose up -d scheduler

docker-once:
	docker compose --profile manual run --rm run-once

docker-dry-run:
	docker compose --profile manual run --rm dry-run