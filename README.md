# FastAPI Simple Redis Cache

A simple and easy-to-use caching library for [FastAPI](https://fastapi.tiangolo.com/) that uses [Redis](https://redis.io/) as a backend.

[![PyPI version](https://img.shields.io/pypi/v/fastapi-simple-redis-cache.svg)](https://pypi.org/project/fastapi-simple-redis-cache/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

-   **Middleware based caching**: Simple middleware extension which will add caching to your API endpoint responses.
-   **Async support**: Fully compatible with FastAPI's `async` routes.
-   **Configurable expiration**: Set cache TTL (Time-To-Live).
-   **Lightweight**: Minimal dependencies and easy to integrate.

## Requirements

*   Python `(>=3.13,<4.0)`
*   FastAPI `(>=0.116.2,<1.0.0)`
*   redis-py `(>=6.4.0,<7.0.0)`

## Installation

Install the package using your favorite package manager: [PyPi Repo available here](https://pypi.org/project/fastapi-simple-redis-cache/)

## How to Use

### Available Parameters

The `NaiveCache` middleware allows you to set certain parameters

#### Necessary Parameters

| Parameter    | Description                                         | Expected Type |
| ------------ | --------------------------------------------------- | ------------- |
| `redis_host` | URL of redis instance to connect to                 | `str`         |
| `redis_port` | Port available to connect at `redis_host`           | `str`         |
| `redis_db`   | Logical database instance at instance to connect to | `int`         |

#### Optional Parameters

| Parameter        | Description                                                                         | Expected Type |
| ---------------- | ----------------------------------------------------------------------------------- | ------------- |
| `redis_username` | Username to use when connecting to redis instance                                   | `str`         |
| `redis_password` | Password to use when connecting to redis instance                                   | `str`         |
| `redis_prefix`   | Custom prefix used for all keys before serializing (defaults to `undefined-prefix`) | `str`         |
| `redis_ttl`      | Time to live in seconds for entries in database (defaults to `300`)                 | `int`         |
| `excluded_paths` | List of strings for paths which should not have their responses cached              | `[str]`       |

### Code Sample

First, you need to initialize the cache and register it with your FastAPI app. This is typically done in your main application file (`main.py`).

```python
# main.py
import random 

from fastapi import FastAPI
from fastapi_simple_redis_cache.NaiveCache import NaiveCache

app = FastAPI()

app.add_middleware(
    NaiveCache,
    redis_host="my_redis_url",
    redis_port="my_redis_port",
    redis_db=0,
    redis_prefix="my_custom_key_prefix",
    excluded_paths=["/do-not-cache-this-path"]
)

@app.get("/")
def return_cached_value():
    """
    Will be random on first call, then cached response returned on all 
    subsequent calls
    """
    return {"message": random.choice(1,2,3,4)}

@app.get("/do-not-cache-this-path")
def return_cached_value():
    """
    Values will not be cached from this endpoint
    """
    return {"message": random.choice(1,2,3,4)}

```

## Additional Features

### Cache-Control
When sending a request to an endpoint, an additional header of `cache-control:no-store` can be provided which will have the middleware skip the addition of the entry to redis.
This feature works regardless of the path being added to the initialized `excluded_paths` parameter

### Response Headers
The `NaiveCache` middleware adds the following response headers for additional information

| Header              | Description                                                                 | Expected Type     |
| ------------------- | --------------------------------------------------------------------------- | ----------------- |
| `x-cache-hit`       | Boolean indicator if the response from the API was retrieved from cache     | `(True \| False)` |
| `x-processing-time` | Time in float seconds that it took for the request/response to be generated | `float`           |

## Misc Notes

This library is a naive implementation of a caching system and is only intended as a primitive implementation for educational usage, it is not recommended to run this in production.

## License

This project is licensed under the MIT License.