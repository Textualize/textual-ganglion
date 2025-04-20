.PHONY: serve
serve:
	DEBUG=1 ganglion serve
deploy-dev:
	fly deploy -c fly-dev.toml
logs-dev:
	fly logs -c fly-dev.toml
deploy-prod:
	fly deploy -c fly-prod.toml --wait-timeout 600
db-prod:
	fly postgres connect -a ganglion-prod-db -c fly-prod.toml
logs-prod:
	fly logs -c fly-prod.toml
restart-prod:
	fly machine restart -c fly-prod.toml
