## v2.0.0 (2026-01-12)

### Feat

- **gh-2**: user only needs to add path relative endpoints on init
- **gh-1**: add more prefix delimiters to redis keys to help determine where keys originate from

## v1.3.3 (2025-09-30)

### Fix

- allow redis protocol prefix in connection information

## v1.3.2 (2025-09-29)

### Fix

- update fastapi dependency range

## v1.3.1 (2025-09-29)

## v1.3.0 (2025-09-28)

### Feat

- add ability to exclude paths from caching

## v1.2.3 (2025-09-28)

### Fix

- utilize more namespaced input value for hashkey

## v1.2.2 (2025-09-28)

### Fix

- change prefix delimiter to be double colon

## v1.2.1 (2025-09-28)

### Fix

- middleware returns expected values when downstream failure occurs

## v1.2.0 (2025-09-27)

### Feat

- gracefully handle requests when unable to connect to redis

## v1.1.1 (2025-09-27)

### Fix

- restructure package for easier utilization when published

## v1.1.0 (2025-09-22)

### Feat

- add optional cache-control header for no-store functionality
- initial featureset with MVP examples
