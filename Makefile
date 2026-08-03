ARCHIVE_ROOT ?= /srv/amigalab
COLLECTION ?= aminet
COLLECTION_PATH = $(ARCHIVE_ROOT)/$(COLLECTION)
COLLECTION_METADATA_PATH = $(ARCHIVE_ROOT)/metadata/collections/$(COLLECTION)

.PHONY: install ansible docker-up docker-down verify backup archive-init manifest verify-archive

install:
	./scripts/bootstrap.sh

ansible:
	ANSIBLE_CONFIG=$(CURDIR)/ansible.cfg ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/site.yml --ask-become-pass

docker-up:
	docker compose --env-file docker/.env -f docker/compose.yaml up -d

docker-down:
	docker compose --env-file docker/.env -f docker/compose.yaml down

verify:
	./scripts/verify.sh

backup:
	./scripts/backup.sh

archive-init: ansible

manifest:
	python3 scripts/build-manifest.py "$(COLLECTION_PATH)" --metadata-dir "$(COLLECTION_METADATA_PATH)"

verify-archive:
	python3 scripts/verify-archive.py "$(COLLECTION_PATH)" --metadata-dir "$(COLLECTION_METADATA_PATH)"
