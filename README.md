# pdf-extractor-service

## Directory layout

```
pdf-extractor-service/
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ core/
│  │   ├─ __init__.py
│  │   ├─ config.py
│  │   ├─ logging_config.py
│  │   ├─ metrics.py
│  │   └─ rate_limit.py
│  ├─ services/
│  │   ├─ __init__.py
│  │   └─ pdf_extractor.py
│  └─ workers/
│      ├─ __init__.py
│      └─ pool.py
├─ tests/
│  ├─ __init__.py
│  ├─ conftest.py
│  └─ test_extractor_service.py
├─ Dockerfile
├─ build.sh
└─ pyproject.toml
```