.PHONY: install report phase1-report phase2-report test check check-phase1 check-phase2 check-brand

install:
	python -m pip install -e '.[report,dev]'

report: phase1-report phase2-report

phase1-report:
	python build_report.py

phase2-report:
	python build_phase2_report.py

test:
	python -m unittest discover -s tests -v

check-phase1: phase1-report
	python scripts/check_report.py

check-phase2: phase2-report test
	python scripts/check_phase2_report.py
	python -m json.tool schemas/morphoia-ir-0.1.schema.json >/dev/null
	python -m json.tool schemas/morphoia-loss-register-0.1.schema.json >/dev/null
	python -m json.tool schemas/morphoia-backend-manifest-0.1.schema.json >/dev/null
	python -m morphoia validate examples/mounting_plate.morph
	morphoia mvx protocol verify

check-brand:
	python scripts/check_pdf_branding.py

check: check-phase1 check-phase2 check-brand
