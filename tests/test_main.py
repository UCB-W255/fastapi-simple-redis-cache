import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from redis import Redis
from testcontainers.redis import RedisContainer

from src.fastapi_simple_redis_cache.NaiveCache import NaiveCache

logger = logging.getLogger(__name__)

REDIS_VERSION = "redis:7"


class SampleInput(BaseModel):
    age: int
    name: str


@pytest.fixture(scope="session")
def redis_fixture():
    """
    Setup a Redis test container for us to interact with throughout our pytests
    """
    with RedisContainer(REDIS_VERSION) as redis_container:
        logger.info("Returning redis IP")
        yield {
            "host": redis_container.get_container_host_ip(),
            "port": redis_container.get_exposed_port(6379),
            "optional_client": redis_container.get_client(),
        }

    logger.info("Closed Redis container context")


@pytest.fixture
def client_fixture(redis_fixture):
    """
    A fixture that provides a TestClient for a FastAPI app with decorated routes.

    Two app instances exist, the sub-application has the middleware enabled for
    caching
    """
    app = FastAPI()
    sub_app = FastAPI()

    app.mount("/subpath", sub_app)
    sub_app.add_middleware(
        NaiveCache,
        redis_host=redis_fixture.get("host"),
        redis_port=redis_fixture.get("port"),
        redis_db=0,
        redis_prefix="pytest-example",
        excluded_paths=["/health"],
    )

    @sub_app.post("/decorated")
    async def decorated_route(input_data: SampleInput):
        input_data.age = 100
        # Simulate sufficiently long computation
        time.sleep(0.25)
        return input_data

    @sub_app.post("/other-decorated")
    async def additional_decorated_route(input_data: SampleInput):
        input_data.age = 999
        # Simulate sufficiently long computation
        time.sleep(0.25)
        return input_data

    @sub_app.get("/health")
    async def health_endpoint():
        return "pong"

    @app.get("/undecorated")
    async def undecorated_route():
        return "Not Decorated"

    # Yield a TestClient for the app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_redis(redis_fixture):
    """
    To ensure stability the Redis instance has its content resets between tests
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")
    redis_testing_client.flushall()


def test_unmodified_route_has_no_header(client_fixture):
    """
    Tests that an undecorated route does not have the custom header.
    """
    response = client_fixture.get("/undecorated")
    assert response.status_code == 200
    assert "x-cache-hit" not in response.headers


def test_middleware_adds_item_to_cache(client_fixture, redis_fixture):
    """
    Tests that the middleware correctly adds an item to the redis cache
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 100}
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "False"

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 1


def test_middleware_returns_item_from_cache(client_fixture, redis_fixture):
    """
    Tests that the middleware correctly adds the value to the cache and that
    the value is also returned from the cache on the second request
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    # First POST
    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 100}
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "False"
    assert float(response.headers["x-processing-time"]) > 0.25

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 1

    # Second POST (Expect Cache Hit)
    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 100}
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "True"
    assert float(response.headers["x-processing-time"]) < 0.25


def test_middleware_respects_cache_control_header(client_fixture, redis_fixture):
    """
    Tests that the middleware respects the "no-store" header and does not store
    the value in the cache if presented with it.
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    # S
    for _ in range(3):
        sample_params = {"name": "Alice", "age": 0}
        response = client_fixture.post(
            "/subpath/decorated",
            json=sample_params,
            headers={"cache-control": "no-store"},
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "False"
        assert float(response.headers["x-processing-time"]) > 0.25
        all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
        assert len(all_keys_in_redis_instance) == 0


def test_middleware_fails_gracefully_when_no_redis_present():
    """
    Ensure that if no valid connection to redis could be established, that the
    middleware fails gracefully and continues to allow operation of the
    underlying application
    """
    unadorned_app = FastAPI()
    unadorned_app.add_middleware(
        NaiveCache,
        redis_host="NONEXISTANT_HOST",
        redis_port=-1,
        redis_db=0,
        redis_prefix="pytest-example",
    )

    @unadorned_app.post("/uncachable_routes")
    async def decorated_route(input_data: SampleInput):
        input_data.age = 100
        return input_data

    # First POST
    sample_params = {"name": "Alice", "age": 0}
    with TestClient(unadorned_app) as unadorned_test_client:
        response = unadorned_test_client.post(
            "/uncachable_routes",
            json=sample_params,
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "False"


def test_middleware_fails_gracefully_on_error_conditions(client_fixture):
    response = client_fixture.get("/not-a-route")
    # The middleware should pass through the 404 from the router
    assert response.status_code == 404

    # This should cause pydantic to raise an error, which should be handled
    # gracefully by the middleware
    invalid_params = {"name": "Alice", "non_existant_field": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=invalid_params,
    )
    assert response.status_code == 422


def test_middleware_adds_unique_cache_values_for_endpoints(
    client_fixture, redis_fixture
):
    """
    Tests that the middleware correctly adds the value to the cache and the
    cache entries are namespaced from each other
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    # First POST
    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 100}
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "False"
    assert float(response.headers["x-processing-time"]) > 0.25

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 1

    # Second POST
    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/other-decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "False"
    assert response.json() == {"name": "Alice", "age": 999}
    assert float(response.headers["x-processing-time"]) > 0.25

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 2


def test_middleware_skips_excluded_paths(client_fixture, redis_fixture):
    """
    Tests that the middleware correctly skips over paths in the ignore list
    """
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    # First POST
    response = client_fixture.get(
        "/subpath/health",
    )
    assert response.status_code == 200

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0


@pytest.mark.parametrize("redis_url_prefix", [("redis://"), ("")])
def test_redis_initialization_works_with_or_without_prefix(
    redis_url_prefix, redis_fixture
):
    test_app = FastAPI()
    test_app.add_middleware(
        NaiveCache,
        redis_host=f"{redis_url_prefix}{redis_fixture.get('host')}",
        redis_port=redis_fixture.get("port"),
        redis_db=0,
        redis_prefix="pytest-example",
    )

    @test_app.post("/simple_hit")
    async def decorated_route(input_data: SampleInput):
        input_data.age = 100
        return input_data

    # First POST
    sample_params = {"name": "Alice", "age": 0}
    with TestClient(test_app) as unadorned_test_client:
        response = unadorned_test_client.post(
            "/simple_hit",
            json=sample_params,
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "False"

        response = unadorned_test_client.post(
            "/simple_hit",
            json=sample_params,
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "True"


def test_prefix_includes_path_and_http_verb(client_fixture, redis_fixture):
    redis_testing_client: Redis = redis_fixture.get("optional_client")

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0

    # First POST
    sample_params = {"name": "Alice", "age": 0}
    response = client_fixture.post(
        "/subpath/decorated",
        json=sample_params,
    )
    assert response.status_code == 200
    assert response.json() == {"name": "Alice", "age": 100}
    assert "x-cache-hit" in response.headers
    assert response.headers["x-cache-hit"] == "False"
    assert float(response.headers["x-processing-time"]) > 0.25

    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 1
    # Ensure path and verb exist
    delimiter_value = "::"
    split_redis_key = (
        all_keys_in_redis_instance[0].decode("utf-8").split(delimiter_value)
    )

    assert len(split_redis_key) == 4
    assert split_redis_key[1] == "POST"
    assert split_redis_key[2] == "/subpath/decorated"


def test_caching_is_skipped_on_excluded_sub_paths(redis_fixture):
    test_app = FastAPI()
    sub_app = FastAPI()

    test_app.mount("/subpath", sub_app)
    sub_app.add_middleware(
        NaiveCache,
        redis_host=f"{redis_fixture.get('host')}",
        redis_port=redis_fixture.get("port"),
        redis_db=0,
        redis_prefix="pytest-example",
        excluded_paths=["/simple_hit"],
    )

    @test_app.post("/simple_hit")
    async def decorated_route(input_data: SampleInput):
        input_data.age = 100
        return input_data

    @sub_app.post("/simple_hit")
    async def skip_route(input_data: SampleInput):
        input_data.age = -1
        return input_data

    sample_params = {"name": "Alice", "age": 0}
    with TestClient(test_app) as test_client:
        # First POST against skipped route
        response = test_client.post(
            "/subpath/simple_hit",
            json=sample_params,
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": -1}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "False"

        response = test_client.post(
            "/subpath/simple_hit",
            json=sample_params,
        )

        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": -1}
        assert "x-cache-hit" in response.headers
        assert response.headers["x-cache-hit"] == "False"

        # Second POST against cached endpoint
        response = test_client.post(
            "/simple_hit",
            json=sample_params,
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}

        response = test_client.post(
            "/simple_hit",
            json=sample_params,
        )

        assert response.status_code == 200
        assert response.json() == {"name": "Alice", "age": 100}

    redis_testing_client: Redis = redis_fixture.get("optional_client")
    all_keys_in_redis_instance = [k for k in redis_testing_client.scan_iter()]
    assert len(all_keys_in_redis_instance) == 0
