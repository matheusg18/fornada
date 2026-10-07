import pytest

from fornada_api.infrastructure.engine import to_async_url


@pytest.mark.parametrize("scheme", ["postgresql", "postgres"])
def test_async_url_keeps_every_part(scheme: str) -> None:
    url = to_async_url(f"{scheme}://fornada:s3cr%40t@postgres:5432/fornada")
    assert url.drivername == "postgresql+psycopg"
    assert url.username == "fornada"
    assert url.password == "s3cr@t"
    assert url.host == "postgres"
    assert url.port == 5432
    assert url.database == "fornada"
