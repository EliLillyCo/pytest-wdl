import pytest


# Prevent the local user's config file from interfering with the tests
@pytest.fixture(scope="session")
def user_config_file():
    return None
