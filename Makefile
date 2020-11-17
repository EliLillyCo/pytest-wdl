repo = EliLillyCo/pytest-wdl
package = pytest_wdl
tests = tests
# Use this option to show full stack trace for errors
#pytestopts = --full-trace
#pytestopts = -ra --tb=short
pytestopts =  -vv --show-capture=all -m "not remote"
#pytestopts = -vv --show-capture=all -m "not integration"

all: clean install install_extras install_development_requirements test test_release_setup

install: clean
	python setup.py bdist_wheel
	pip install --upgrade dist/*.whl $(installargs)

install_development_requirements:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

install_extras:
	pip install .[all]

test:
	env PYTHONPATH="." coverage run -m pytest -p pytester $(pytestopts) $(tests)
	coverage report -m
	coverage xml

test_release_setup:
	twine check dist/*

lint:
	flake8 $(package)

reformat:
	black $(package)
	black $(tests)

clean:
	rm -f .coverage
	rm -f coverage.xml
	rm -Rf .eggs
	rm -Rf .pytest_cache
	rm -Rf __pycache__
	rm -Rf **/__pycache__/*
	rm -Rf **/*.c
	rm -Rf **/*.so
	rm -Rf **/*.pyc
	rm -Rf dist/
	rm -Rf build/
	rm -Rf docs/build
	rm -Rf $(package).egg-info
	rm -Rf cromwell-workflow-logs

tag:
	git tag $(version)

push_tag:
	git push origin --tags

del_tag:
	git tag -d $(version)

pypi_release:
	# create source distribution
	python setup.py sdist
	# PyPI release
	python setup.py sdist upload -r omics-pypi

release: clean tag
	${MAKE} install install_extras test pypi_release push_tag || (${MAKE} del_tag && exit 1)

	# GitHub release
	curl -v -i -X POST \
		-H "Content-Type:application/json" \
		-H "Authorization: token $(token)" \
		https://api.github.com/repos/$(repo)/releases \
		-d '{"tag_name":"$(version)","target_commitish": "main","name": "$(version)","body": "$(desc)","draft": false,"prerelease": false}'
