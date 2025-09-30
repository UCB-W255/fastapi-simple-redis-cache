import logging
import time
import hashlib

import redis
from fastapi import Request
from fastapi.responses import Response
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import ConnectionError
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class NaiveCache(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        redis_host=None,
        redis_port=None,
        redis_db=None,
        redis_username=None,
        redis_password=None,
        redis_prefix="undefined-prefix",
        redis_ttl=300,
        excluded_paths=[],
    ):
        if not all([redis_host, redis_port, redis_db is not None]):
            raise ValueError(
                f"Configuration to connect to redis is incomplete: {redis_host=},{redis_port=},{redis_db=}"
            )
        super().__init__(app)

        logger.info(
            f"Attempting to connect to redis at {redis_host}:{redis_port}/{redis_db} with username {redis_username}"
        )
        try:
            self.redis_client = redis.Redis(
                host=redis_host.removeprefix("redis://"),
                port=redis_port,
                db=redis_db,
                username=redis_username,
                password=redis_password,
                retry=Retry(ExponentialBackoff(cap=10, base=1), retries=10),
                decode_responses=True,
            )
            self.store_prefix = redis_prefix
            self.store_ttl = redis_ttl
            self.excluded_paths = excluded_paths
            logger.info(f"Redis ping response: {self.redis_client.ping()}")
        except ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}")
            self.redis_client = None

    async def dispatch(self, request: Request, call_next):
        logger.info("Executing Redis Cache Middleware")

        start_time = time.perf_counter()
        if not self.redis_client:
            logger.info("No redis connection established, skipping cache attempts")
            CACHE_SHOULD_STORE_FLAG = False
        elif request.headers.get("cache-control") == "no-store":
            logger.info("cache-control set to no-store, skipping cache attempts")
            CACHE_SHOULD_STORE_FLAG = False
        elif request.url.path in self.excluded_paths:
            logger.info(
                "External request hitting path in excluded paths, skipping cache attempts"
            )
            CACHE_SHOULD_STORE_FLAG = False
        else:
            CACHE_SHOULD_STORE_FLAG = True

        SHOULD_RUN_DOWNSTREAM = True
        # ==========================================
        logger.info(f"{request.headers.get("cache-control")=}")
        if CACHE_SHOULD_STORE_FLAG:
            request_content = f"{request.method}:{request.url.path}:{request.query_params}:{await request.body()}"
            requested_content_hash = self.hashkey_generator(request_content)

            logger.info(f"{requested_content_hash} Checking for value in redis")
            returned_redis_content = self.redis_client.get(requested_content_hash)

            if not returned_redis_content:
                logger.info(f"{requested_content_hash} NOT FOUND")
                SHOULD_RUN_DOWNSTREAM = True

            else:
                SHOULD_RUN_DOWNSTREAM = False
                logger.info(f"{requested_content_hash} FOUND")
                response = Response(
                    content=returned_redis_content,
                    media_type="application/json",
                    headers={"x-cache-hit": "True"},
                )

        if SHOULD_RUN_DOWNSTREAM:
            logger.info("Running downstream function")
            function_response = await call_next(request)

            if function_response.status_code != 200:
                # Early exit before attempting to store bad values in redis
                return function_response

            # Extract body from function response iterator
            chunks = [chunk async for chunk in function_response.body_iterator]
            response_body = b"".join(chunks)

            if CACHE_SHOULD_STORE_FLAG:
                self.redis_client.set(
                    requested_content_hash, response_body, ex=self.store_ttl
                )
                logger.info(f"{requested_content_hash} SET")

            # We need to build a new response since we consumed the body_iterator.
            response = Response(
                content=response_body,
                status_code=function_response.status_code,
                headers=dict(function_response.headers),
                media_type=function_response.media_type,
            )
            response.headers["x-cache-hit"] = "False"

        processing_time = time.perf_counter() - start_time
        response.headers["x-processing-time"] = str(processing_time)
        return response

    def hashkey_generator(self, input_str) -> str:
        hashed_hex = hashlib.sha256(input_str.encode("utf-8")).hexdigest()
        return f"{self.store_prefix}::{hashed_hex}"
