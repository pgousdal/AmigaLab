.PHONY: install ansible docker-up docker-down verify backup

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
