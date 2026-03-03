.PHONY: install deploy upgrade uninstall status \
        logs-sf logs-opl logs-ww logs-sub logs-go2rtc

install:
	sudo bash scripts/install-k3s.sh

deploy:
	bash scripts/deploy.sh

upgrade:
	helm upgrade smartfield charts/smartfield --namespace smartfield --wait

uninstall:
	helm uninstall smartfield --namespace smartfield

status:
	kubectl -n smartfield get pods -o wide

logs-sf:
	kubectl -n smartfield logs -f deployment/smartfields

logs-opl:
	kubectl -n smartfield logs -f deployment/openpasslite

logs-ww:
	kubectl -n smartfield logs -f deployment/wildwings

logs-sub:
	kubectl -n smartfield logs -f deployment/mqtt-subscriber

logs-go2rtc:
	kubectl -n smartfield logs -f deployment/go2rtc
