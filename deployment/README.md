# BetterGovPH Data Visualizations - Deployment Guide

## Systemd Services

The application consists of two services:

1. **visualization.service** - Rust ActixWeb frontend (port 8889)
2. **visualization_api.service** - Python FastAPI backend (port 8000)

### Installation



### Service Configuration

- **User**: joebert (adjust for your deployment)
- **Working Directory**: 
- **Environment File**:  in the working directory

## Environment Setup

1. Create  file based on your environment requirements
2. Ensure the service user has read access to the file
3. Update paths and ports for your specific deployment

## Nginx Configuration

Configure nginx as a reverse proxy:



## Build Process

Defaulting to user installation because normal site-packages is not writeable
Requirement already satisfied: fastapi in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 1)) (0.116.1)
Requirement already satisfied: uvicorn in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 2)) (0.35.0)
Requirement already satisfied: openai in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 3)) (1.106.1)
Requirement already satisfied: sentence-transformers in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 4)) (5.1.0)
Requirement already satisfied: numpy in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 5)) (1.26.4)
Requirement already satisfied: requests in /usr/lib/python3/dist-packages (from -r requirements.txt (line 6)) (2.25.1)
Requirement already satisfied: httpx in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 7)) (0.28.1)
Requirement already satisfied: pydantic in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 8)) (2.11.7)
Requirement already satisfied: python-multipart in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 9)) (0.0.20)
Requirement already satisfied: pymongo in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 10)) (4.15.0)
Requirement already satisfied: aiohttp in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 11)) (3.12.15)
Requirement already satisfied: pandas in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 12)) (2.3.2)
Collecting motor
  Using cached motor-3.7.1-py3-none-any.whl (74 kB)
Requirement already satisfied: python-dotenv in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 14)) (1.1.1)
Collecting python-magic
  Using cached python_magic-0.4.27-py2.py3-none-any.whl (13 kB)
Collecting meilisearch
  Using cached meilisearch-0.37.0-py3-none-any.whl (29 kB)
Requirement already satisfied: paypalrestsdk in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 17)) (1.13.3)
Requirement already satisfied: xendit in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 18)) (0.1.3)
Collecting mollie-api-python
  Downloading mollie_api_python-3.9.0-py3-none-any.whl (52 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 52.6/52.6 KB 3.3 MB/s eta 0:00:00
Requirement already satisfied: jinja2 in /usr/lib/python3/dist-packages (from -r requirements.txt (line 20)) (3.0.3)
Requirement already satisfied: python-dateutil in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 21)) (2.9.0.post0)
Requirement already satisfied: typing-extensions in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 22)) (4.15.0)
Requirement already satisfied: dnspython in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 23)) (2.8.0)
Requirement already satisfied: starlette in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 26)) (0.47.3)
Requirement already satisfied: itsdangerous in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 27)) (2.2.0)
Requirement already satisfied: bcrypt in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 28)) (4.3.0)
Requirement already satisfied: playwright in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 29)) (1.40.0)
Collecting scholarly
  Using cached scholarly-1.7.11-py3-none-any.whl (39 kB)
Collecting python-docx
  Using cached python_docx-1.2.0-py3-none-any.whl (252 kB)
Collecting docx2txt
  Using cached docx2txt-0.9-py3-none-any.whl (4.0 kB)
Requirement already satisfied: openpyxl in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 37)) (3.1.5)
Collecting xlrd
  Using cached xlrd-2.0.2-py2.py3-none-any.whl (96 kB)
Requirement already satisfied: PyPDF2 in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 40)) (3.0.1)
Requirement already satisfied: pdfplumber in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 41)) (0.11.7)
Requirement already satisfied: chromadb in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 44)) (1.0.21)
Requirement already satisfied: asyncpg in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 47)) (0.30.0)
Requirement already satisfied: psycopg2-binary in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 48)) (2.9.10)
Requirement already satisfied: psutil in /usr/lib/python3/dist-packages (from -r requirements.txt (line 51)) (5.9.0)
Requirement already satisfied: aiofiles in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 52)) (23.2.1)
Requirement already satisfied: paramiko in /home/joebert/.local/lib/python3.10/site-packages (from -r requirements.txt (line 55)) (4.0.0)
Collecting pycodestyle
  Using cached pycodestyle-2.14.0-py2.py3-none-any.whl (31 kB)
Requirement already satisfied: h11>=0.8 in /home/joebert/.local/lib/python3.10/site-packages (from uvicorn->-r requirements.txt (line 2)) (0.16.0)
Requirement already satisfied: click>=7.0 in /usr/lib/python3/dist-packages (from uvicorn->-r requirements.txt (line 2)) (8.0.3)
Requirement already satisfied: sniffio in /home/joebert/.local/lib/python3.10/site-packages (from openai->-r requirements.txt (line 3)) (1.3.1)
Requirement already satisfied: jiter<1,>=0.4.0 in /home/joebert/.local/lib/python3.10/site-packages (from openai->-r requirements.txt (line 3)) (0.10.0)
Requirement already satisfied: distro<2,>=1.7.0 in /usr/lib/python3/dist-packages (from openai->-r requirements.txt (line 3)) (1.7.0)
Requirement already satisfied: tqdm>4 in /home/joebert/.local/lib/python3.10/site-packages (from openai->-r requirements.txt (line 3)) (4.67.1)
Requirement already satisfied: anyio<5,>=3.5.0 in /home/joebert/.local/lib/python3.10/site-packages (from openai->-r requirements.txt (line 3)) (4.10.0)
Requirement already satisfied: transformers<5.0.0,>=4.41.0 in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (4.56.1)
Requirement already satisfied: huggingface-hub>=0.20.0 in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (0.34.4)
Requirement already satisfied: Pillow in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (10.4.0)
Requirement already satisfied: scipy in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (1.15.3)
Requirement already satisfied: scikit-learn in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (1.7.2)
Requirement already satisfied: torch>=1.11.0 in /home/joebert/.local/lib/python3.10/site-packages (from sentence-transformers->-r requirements.txt (line 4)) (2.8.0)
Requirement already satisfied: certifi in /home/joebert/.local/lib/python3.10/site-packages (from httpx->-r requirements.txt (line 7)) (2025.8.3)
Requirement already satisfied: httpcore==1.* in /home/joebert/.local/lib/python3.10/site-packages (from httpx->-r requirements.txt (line 7)) (1.0.9)
Requirement already satisfied: idna in /usr/lib/python3/dist-packages (from httpx->-r requirements.txt (line 7)) (3.3)
Requirement already satisfied: annotated-types>=0.6.0 in /home/joebert/.local/lib/python3.10/site-packages (from pydantic->-r requirements.txt (line 8)) (0.7.0)
Requirement already satisfied: typing-inspection>=0.4.0 in /home/joebert/.local/lib/python3.10/site-packages (from pydantic->-r requirements.txt (line 8)) (0.4.1)
Requirement already satisfied: pydantic-core==2.33.2 in /home/joebert/.local/lib/python3.10/site-packages (from pydantic->-r requirements.txt (line 8)) (2.33.2)
Requirement already satisfied: async-timeout<6.0,>=4.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (5.0.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (1.20.1)
Requirement already satisfied: aiosignal>=1.4.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (1.4.0)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (2.6.1)
Requirement already satisfied: frozenlist>=1.1.1 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (1.7.0)
Requirement already satisfied: propcache>=0.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (0.3.2)
Requirement already satisfied: multidict<7.0,>=4.5 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (6.6.4)
Requirement already satisfied: attrs>=17.3.0 in /home/joebert/.local/lib/python3.10/site-packages (from aiohttp->-r requirements.txt (line 11)) (25.3.0)
Requirement already satisfied: tzdata>=2022.7 in /home/joebert/.local/lib/python3.10/site-packages (from pandas->-r requirements.txt (line 12)) (2025.2)
Requirement already satisfied: pytz>=2020.1 in /usr/lib/python3/dist-packages (from pandas->-r requirements.txt (line 12)) (2022.1)
Collecting camel-converter[pydantic]
  Downloading camel_converter-5.0.0-py3-none-any.whl (6.3 kB)
Requirement already satisfied: six>=1.0.0 in /usr/lib/python3/dist-packages (from paypalrestsdk->-r requirements.txt (line 17)) (1.16.0)
Requirement already satisfied: pyopenssl>=0.15 in /usr/lib/python3/dist-packages (from paypalrestsdk->-r requirements.txt (line 17)) (21.0.0)
Requirement already satisfied: pytest-cov<3.0.0,>=2.10.0 in /home/joebert/.local/lib/python3.10/site-packages (from xendit->-r requirements.txt (line 18)) (2.12.1)
Requirement already satisfied: requests_oauthlib in /home/joebert/.local/lib/python3.10/site-packages (from mollie-api-python->-r requirements.txt (line 19)) (2.0.0)
Requirement already satisfied: urllib3 in /home/joebert/.local/lib/python3.10/site-packages (from mollie-api-python->-r requirements.txt (line 19)) (2.5.0)
Requirement already satisfied: pyee==11.0.1 in /home/joebert/.local/lib/python3.10/site-packages (from playwright->-r requirements.txt (line 29)) (11.0.1)
Requirement already satisfied: greenlet==3.0.1 in /home/joebert/.local/lib/python3.10/site-packages (from playwright->-r requirements.txt (line 29)) (3.0.1)
Requirement already satisfied: selenium in /home/joebert/.local/lib/python3.10/site-packages (from scholarly->-r requirements.txt (line 32)) (4.36.0)
Collecting sphinx-rtd-theme
  Using cached sphinx_rtd_theme-3.0.2-py2.py3-none-any.whl (7.7 MB)
Collecting deprecated
  Using cached Deprecated-1.2.18-py2.py3-none-any.whl (10.0 kB)
Collecting arrow
  Using cached arrow-1.3.0-py3-none-any.whl (66 kB)
Requirement already satisfied: beautifulsoup4 in /home/joebert/.local/lib/python3.10/site-packages (from scholarly->-r requirements.txt (line 32)) (4.14.2)
Collecting free-proxy
  Using cached free_proxy-1.1.3.tar.gz (5.6 kB)
  Preparing metadata (setup.py): started
  Preparing metadata (setup.py): finished with status done
Collecting bibtexparser
  Using cached bibtexparser-1.4.3.tar.gz (55 kB)
  Preparing metadata (setup.py): started
  Preparing metadata (setup.py): finished with status done
Collecting fake-useragent
  Using cached fake_useragent-2.2.0-py3-none-any.whl (161 kB)
Collecting lxml>=3.1.0
  Downloading lxml-6.0.2-cp310-cp310-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl (5.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 5.3/5.3 MB 60.7 MB/s eta 0:00:00
Requirement already satisfied: et-xmlfile in /home/joebert/.local/lib/python3.10/site-packages (from openpyxl->-r requirements.txt (line 37)) (2.0.0)
Requirement already satisfied: pypdfium2>=4.18.0 in /home/joebert/.local/lib/python3.10/site-packages (from pdfplumber->-r requirements.txt (line 41)) (4.30.0)
Requirement already satisfied: pdfminer.six==20250506 in /home/joebert/.local/lib/python3.10/site-packages (from pdfplumber->-r requirements.txt (line 41)) (20250506)
Requirement already satisfied: charset-normalizer>=2.0.0 in /home/joebert/.local/lib/python3.10/site-packages (from pdfminer.six==20250506->pdfplumber->-r requirements.txt (line 41)) (3.4.3)
Requirement already satisfied: cryptography>=36.0.0 in /home/joebert/.local/lib/python3.10/site-packages (from pdfminer.six==20250506->pdfplumber->-r requirements.txt (line 41)) (46.0.2)
Requirement already satisfied: rich>=10.11.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (14.1.0)
Requirement already satisfied: onnxruntime>=1.14.1 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.22.1)
Requirement already satisfied: tenacity>=8.2.3 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (9.1.2)
Requirement already satisfied: pypika>=0.48.9 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (0.48.9)
Requirement already satisfied: tokenizers>=0.13.2 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (0.22.0)
Requirement already satisfied: overrides>=7.3.1 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (7.7.0)
Requirement already satisfied: opentelemetry-sdk>=1.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.37.0)
Requirement already satisfied: build>=1.0.3 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.3.0)
Requirement already satisfied: orjson>=3.9.12 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (3.11.3)
Requirement already satisfied: posthog<6.0.0,>=2.4.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (5.4.0)
Requirement already satisfied: pybase64>=1.4.1 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.4.2)
Requirement already satisfied: pyyaml>=6.0.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (6.0.2)
Requirement already satisfied: typer>=0.9.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (0.17.4)
Requirement already satisfied: jsonschema>=4.19.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (4.25.1)
Requirement already satisfied: kubernetes>=28.1.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (33.1.0)
Requirement already satisfied: grpcio>=1.58.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.74.0)
Requirement already satisfied: importlib-resources in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (6.5.2)
Requirement already satisfied: opentelemetry-api>=1.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.37.0)
Requirement already satisfied: opentelemetry-exporter-otlp-proto-grpc>=1.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (1.37.0)
Requirement already satisfied: mmh3>=4.0.1 in /home/joebert/.local/lib/python3.10/site-packages (from chromadb->-r requirements.txt (line 44)) (5.2.0)
Requirement already satisfied: pynacl>=1.5 in /home/joebert/.local/lib/python3.10/site-packages (from paramiko->-r requirements.txt (line 55)) (1.6.0)
Requirement already satisfied: invoke>=2.0 in /home/joebert/.local/lib/python3.10/site-packages (from paramiko->-r requirements.txt (line 55)) (2.2.0)
Requirement already satisfied: exceptiongroup>=1.0.2 in /home/joebert/.local/lib/python3.10/site-packages (from anyio<5,>=3.5.0->openai->-r requirements.txt (line 3)) (1.3.0)
Requirement already satisfied: pyproject_hooks in /home/joebert/.local/lib/python3.10/site-packages (from build>=1.0.3->chromadb->-r requirements.txt (line 44)) (1.2.0)
Requirement already satisfied: tomli>=1.1.0 in /home/joebert/.local/lib/python3.10/site-packages (from build>=1.0.3->chromadb->-r requirements.txt (line 44)) (2.2.1)
Requirement already satisfied: packaging>=19.1 in /home/joebert/.local/lib/python3.10/site-packages (from build>=1.0.3->chromadb->-r requirements.txt (line 44)) (25.0)
Requirement already satisfied: cffi>=2.0.0 in /home/joebert/.local/lib/python3.10/site-packages (from cryptography>=36.0.0->pdfminer.six==20250506->pdfplumber->-r requirements.txt (line 41)) (2.0.0)
Requirement already satisfied: fsspec>=2023.5.0 in /home/joebert/.local/lib/python3.10/site-packages (from huggingface-hub>=0.20.0->sentence-transformers->-r requirements.txt (line 4)) (2025.9.0)
Requirement already satisfied: hf-xet<2.0.0,>=1.1.3 in /home/joebert/.local/lib/python3.10/site-packages (from huggingface-hub>=0.20.0->sentence-transformers->-r requirements.txt (line 4)) (1.1.9)
Requirement already satisfied: filelock in /home/joebert/.local/lib/python3.10/site-packages (from huggingface-hub>=0.20.0->sentence-transformers->-r requirements.txt (line 4)) (3.19.1)
Requirement already satisfied: jsonschema-specifications>=2023.03.6 in /home/joebert/.local/lib/python3.10/site-packages (from jsonschema>=4.19.0->chromadb->-r requirements.txt (line 44)) (2025.9.1)
Requirement already satisfied: referencing>=0.28.4 in /home/joebert/.local/lib/python3.10/site-packages (from jsonschema>=4.19.0->chromadb->-r requirements.txt (line 44)) (0.36.2)
Requirement already satisfied: rpds-py>=0.7.1 in /home/joebert/.local/lib/python3.10/site-packages (from jsonschema>=4.19.0->chromadb->-r requirements.txt (line 44)) (0.27.1)
Requirement already satisfied: durationpy>=0.7 in /home/joebert/.local/lib/python3.10/site-packages (from kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (0.10)
Requirement already satisfied: oauthlib>=3.2.2 in /home/joebert/.local/lib/python3.10/site-packages (from kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (3.3.1)
Requirement already satisfied: websocket-client!=0.40.0,!=0.41.*,!=0.42.*,>=0.32.0 in /home/joebert/.local/lib/python3.10/site-packages (from kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (1.8.0)
Requirement already satisfied: google-auth>=1.0.1 in /home/joebert/.local/lib/python3.10/site-packages (from kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (2.40.3)
Requirement already satisfied: sympy in /home/joebert/.local/lib/python3.10/site-packages (from onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (1.14.0)
Requirement already satisfied: protobuf in /home/joebert/.local/lib/python3.10/site-packages (from onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (6.32.1)
Requirement already satisfied: coloredlogs in /home/joebert/.local/lib/python3.10/site-packages (from onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (15.0.1)
Requirement already satisfied: flatbuffers in /home/joebert/.local/lib/python3.10/site-packages (from onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (25.2.10)
Requirement already satisfied: importlib-metadata<8.8.0,>=6.0 in /home/joebert/.local/lib/python3.10/site-packages (from opentelemetry-api>=1.2.0->chromadb->-r requirements.txt (line 44)) (8.7.0)
Requirement already satisfied: googleapis-common-protos~=1.57 in /home/joebert/.local/lib/python3.10/site-packages (from opentelemetry-exporter-otlp-proto-grpc>=1.2.0->chromadb->-r requirements.txt (line 44)) (1.70.0)
Requirement already satisfied: opentelemetry-exporter-otlp-proto-common==1.37.0 in /home/joebert/.local/lib/python3.10/site-packages (from opentelemetry-exporter-otlp-proto-grpc>=1.2.0->chromadb->-r requirements.txt (line 44)) (1.37.0)
Requirement already satisfied: opentelemetry-proto==1.37.0 in /home/joebert/.local/lib/python3.10/site-packages (from opentelemetry-exporter-otlp-proto-grpc>=1.2.0->chromadb->-r requirements.txt (line 44)) (1.37.0)
Requirement already satisfied: opentelemetry-semantic-conventions==0.58b0 in /home/joebert/.local/lib/python3.10/site-packages (from opentelemetry-sdk>=1.2.0->chromadb->-r requirements.txt (line 44)) (0.58b0)
Requirement already satisfied: backoff>=1.10.0 in /home/joebert/.local/lib/python3.10/site-packages (from posthog<6.0.0,>=2.4.0->chromadb->-r requirements.txt (line 44)) (2.2.1)
Requirement already satisfied: toml in /home/joebert/.local/lib/python3.10/site-packages (from pytest-cov<3.0.0,>=2.10.0->xendit->-r requirements.txt (line 18)) (0.10.2)
Requirement already satisfied: coverage>=5.2.1 in /home/joebert/.local/lib/python3.10/site-packages (from pytest-cov<3.0.0,>=2.10.0->xendit->-r requirements.txt (line 18)) (7.10.6)
Requirement already satisfied: pytest>=4.6 in /home/joebert/.local/lib/python3.10/site-packages (from pytest-cov<3.0.0,>=2.10.0->xendit->-r requirements.txt (line 18)) (8.4.2)
Requirement already satisfied: markdown-it-py>=2.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from rich>=10.11.0->chromadb->-r requirements.txt (line 44)) (4.0.0)
Requirement already satisfied: pygments<3.0.0,>=2.13.0 in /home/joebert/.local/lib/python3.10/site-packages (from rich>=10.11.0->chromadb->-r requirements.txt (line 44)) (2.19.2)
Requirement already satisfied: nvidia-nvtx-cu12==12.8.90 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.90)
Requirement already satisfied: nvidia-cuda-runtime-cu12==12.8.90 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.90)
Requirement already satisfied: nvidia-cusolver-cu12==11.7.3.90 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (11.7.3.90)
Requirement already satisfied: nvidia-curand-cu12==10.3.9.90 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (10.3.9.90)
Requirement already satisfied: nvidia-cuda-nvrtc-cu12==12.8.93 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.93)
Requirement already satisfied: nvidia-cublas-cu12==12.8.4.1 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.4.1)
Requirement already satisfied: nvidia-nccl-cu12==2.27.3 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (2.27.3)
Requirement already satisfied: nvidia-cusparselt-cu12==0.7.1 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (0.7.1)
Requirement already satisfied: networkx in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (3.4.2)
Requirement already satisfied: nvidia-cudnn-cu12==9.10.2.21 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (9.10.2.21)
Requirement already satisfied: nvidia-cufile-cu12==1.13.1.3 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (1.13.1.3)
Requirement already satisfied: nvidia-cufft-cu12==11.3.3.83 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (11.3.3.83)
Requirement already satisfied: nvidia-cuda-cupti-cu12==12.8.90 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.90)
Requirement already satisfied: nvidia-cusparse-cu12==12.5.8.93 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.5.8.93)
Requirement already satisfied: nvidia-nvjitlink-cu12==12.8.93 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (12.8.93)
Requirement already satisfied: triton==3.4.0 in /home/joebert/.local/lib/python3.10/site-packages (from torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (3.4.0)
Requirement already satisfied: setuptools>=40.8.0 in /usr/lib/python3/dist-packages (from triton==3.4.0->torch>=1.11.0->sentence-transformers->-r requirements.txt (line 4)) (59.6.0)
Requirement already satisfied: regex!=2019.12.17 in /home/joebert/.local/lib/python3.10/site-packages (from transformers<5.0.0,>=4.41.0->sentence-transformers->-r requirements.txt (line 4)) (2025.9.1)
Requirement already satisfied: safetensors>=0.4.3 in /home/joebert/.local/lib/python3.10/site-packages (from transformers<5.0.0,>=4.41.0->sentence-transformers->-r requirements.txt (line 4)) (0.6.2)
Requirement already satisfied: shellingham>=1.3.0 in /home/joebert/.local/lib/python3.10/site-packages (from typer>=0.9.0->chromadb->-r requirements.txt (line 44)) (1.5.4)
Requirement already satisfied: websockets>=10.4 in /home/joebert/.local/lib/python3.10/site-packages (from uvicorn->-r requirements.txt (line 2)) (11.0.3)
Requirement already satisfied: watchfiles>=0.13 in /home/joebert/.local/lib/python3.10/site-packages (from uvicorn->-r requirements.txt (line 2)) (1.1.0)
Requirement already satisfied: uvloop>=0.15.1 in /home/joebert/.local/lib/python3.10/site-packages (from uvicorn->-r requirements.txt (line 2)) (0.21.0)
Requirement already satisfied: httptools>=0.6.3 in /home/joebert/.local/lib/python3.10/site-packages (from uvicorn->-r requirements.txt (line 2)) (0.6.4)
Collecting types-python-dateutil>=2.8.10
  Downloading types_python_dateutil-2.9.0.20251008-py3-none-any.whl (17 kB)
Requirement already satisfied: soupsieve>1.2 in /home/joebert/.local/lib/python3.10/site-packages (from beautifulsoup4->scholarly->-r requirements.txt (line 32)) (2.8)
Requirement already satisfied: pyparsing>=2.0.3 in /usr/lib/python3/dist-packages (from bibtexparser->scholarly->-r requirements.txt (line 32)) (2.4.7)
Collecting wrapt<2,>=1.10
  Using cached wrapt-1.17.3-cp310-cp310-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (81 kB)
Requirement already satisfied: PySocks!=1.5.7,>=1.5.6 in /home/joebert/.local/lib/python3.10/site-packages (from requests->-r requirements.txt (line 6)) (1.7.1)
Requirement already satisfied: joblib>=1.2.0 in /home/joebert/.local/lib/python3.10/site-packages (from scikit-learn->sentence-transformers->-r requirements.txt (line 4)) (1.5.2)
Requirement already satisfied: threadpoolctl>=3.1.0 in /home/joebert/.local/lib/python3.10/site-packages (from scikit-learn->sentence-transformers->-r requirements.txt (line 4)) (3.6.0)
Requirement already satisfied: trio-websocket<1.0,>=0.12.2 in /home/joebert/.local/lib/python3.10/site-packages (from selenium->scholarly->-r requirements.txt (line 32)) (0.12.2)
Requirement already satisfied: trio<1.0,>=0.30.0 in /home/joebert/.local/lib/python3.10/site-packages (from selenium->scholarly->-r requirements.txt (line 32)) (0.31.0)
Collecting sphinx<9,>=6
  Using cached sphinx-8.1.3-py3-none-any.whl (3.5 MB)
Collecting sphinxcontrib-jquery<5,>=4
  Using cached sphinxcontrib_jquery-4.1-py2.py3-none-any.whl (121 kB)
Collecting docutils<0.22,>0.18
  Using cached docutils-0.21.2-py3-none-any.whl (587 kB)
Requirement already satisfied: pycparser in /home/joebert/.local/lib/python3.10/site-packages (from cffi>=2.0.0->cryptography>=36.0.0->pdfminer.six==20250506->pdfplumber->-r requirements.txt (line 41)) (2.23)
Requirement already satisfied: pyasn1-modules>=0.2.1 in /usr/lib/python3/dist-packages (from google-auth>=1.0.1->kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (0.2.1)
Requirement already satisfied: rsa<5,>=3.1.4 in /home/joebert/.local/lib/python3.10/site-packages (from google-auth>=1.0.1->kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (4.9.1)
Requirement already satisfied: cachetools<6.0,>=2.0.0 in /home/joebert/.local/lib/python3.10/site-packages (from google-auth>=1.0.1->kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (5.5.2)
Requirement already satisfied: zipp>=3.20 in /home/joebert/.local/lib/python3.10/site-packages (from importlib-metadata<8.8.0,>=6.0->opentelemetry-api>=1.2.0->chromadb->-r requirements.txt (line 44)) (3.23.0)
Requirement already satisfied: mdurl~=0.1 in /home/joebert/.local/lib/python3.10/site-packages (from markdown-it-py>=2.2.0->rich>=10.11.0->chromadb->-r requirements.txt (line 44)) (0.1.2)
Requirement already satisfied: iniconfig>=1 in /home/joebert/.local/lib/python3.10/site-packages (from pytest>=4.6->pytest-cov<3.0.0,>=2.10.0->xendit->-r requirements.txt (line 18)) (2.1.0)
Requirement already satisfied: pluggy<2,>=1.5 in /home/joebert/.local/lib/python3.10/site-packages (from pytest>=4.6->pytest-cov<3.0.0,>=2.10.0->xendit->-r requirements.txt (line 18)) (1.6.0)
Collecting sphinx<9,>=6
  Downloading sphinx-8.1.2-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 77.9 MB/s eta 0:00:00
  Downloading sphinx-8.1.1-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 77.6 MB/s eta 0:00:00
  Downloading sphinx-8.1.0-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 27.3 MB/s eta 0:00:00
  Downloading sphinx-8.0.2-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 79.1 MB/s eta 0:00:00
  Downloading sphinx-8.0.1-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 87.1 MB/s eta 0:00:00
  Downloading sphinx-8.0.0-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 82.2 MB/s eta 0:00:00
  Downloading sphinx-7.4.7-py3-none-any.whl (3.4 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.4/3.4 MB 77.5 MB/s eta 0:00:00
  Downloading sphinx-7.4.6-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 78.1 MB/s eta 0:00:00
  Downloading sphinx-7.4.5-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 18.1 MB/s eta 0:00:00
  Downloading sphinx-7.4.4-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 26.1 MB/s eta 0:00:00
  Downloading sphinx-7.4.3-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 83.1 MB/s eta 0:00:00
  Downloading sphinx-7.4.2-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 30.3 MB/s eta 0:00:00
  Downloading sphinx-7.4.1-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 31.8 MB/s eta 0:00:00
  Downloading sphinx-7.4.0-py3-none-any.whl (3.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.5/3.5 MB 28.4 MB/s eta 0:00:00
  Downloading sphinx-7.3.7-py3-none-any.whl (3.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.3/3.3 MB 80.3 MB/s eta 0:00:00
Collecting alabaster~=0.7.14
  Downloading alabaster-0.7.16-py3-none-any.whl (13 kB)
Collecting snowballstemmer>=2.0
  Using cached snowballstemmer-3.0.1-py3-none-any.whl (103 kB)
Collecting sphinxcontrib-applehelp
  Using cached sphinxcontrib_applehelp-2.0.0-py3-none-any.whl (119 kB)
Collecting imagesize>=1.3
  Using cached imagesize-1.4.1-py2.py3-none-any.whl (8.8 kB)
Collecting sphinxcontrib-qthelp
  Using cached sphinxcontrib_qthelp-2.0.0-py3-none-any.whl (88 kB)
Collecting sphinxcontrib-jsmath
  Using cached sphinxcontrib_jsmath-1.0.1-py2.py3-none-any.whl (5.1 kB)
Collecting sphinxcontrib-devhelp
  Using cached sphinxcontrib_devhelp-2.0.0-py3-none-any.whl (82 kB)
Collecting sphinxcontrib-htmlhelp>=2.0.0
  Using cached sphinxcontrib_htmlhelp-2.1.0-py3-none-any.whl (98 kB)
Collecting sphinxcontrib-serializinghtml>=1.1.9
  Using cached sphinxcontrib_serializinghtml-2.0.0-py3-none-any.whl (92 kB)
Collecting babel>=2.9
  Using cached babel-2.17.0-py3-none-any.whl (10.2 MB)
Requirement already satisfied: mpmath<1.4,>=1.1.0 in /home/joebert/.local/lib/python3.10/site-packages (from sympy->onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (1.3.0)
Requirement already satisfied: outcome in /home/joebert/.local/lib/python3.10/site-packages (from trio<1.0,>=0.30.0->selenium->scholarly->-r requirements.txt (line 32)) (1.3.0.post0)
Requirement already satisfied: sortedcontainers in /home/joebert/.local/lib/python3.10/site-packages (from trio<1.0,>=0.30.0->selenium->scholarly->-r requirements.txt (line 32)) (2.4.0)
Requirement already satisfied: wsproto>=0.14 in /usr/lib/python3/dist-packages (from trio-websocket<1.0,>=0.12.2->selenium->scholarly->-r requirements.txt (line 32)) (1.0.0)
Requirement already satisfied: humanfriendly>=9.1 in /home/joebert/.local/lib/python3.10/site-packages (from coloredlogs->onnxruntime>=1.14.1->chromadb->-r requirements.txt (line 44)) (10.0)
Requirement already satisfied: pyasn1>=0.1.3 in /usr/lib/python3/dist-packages (from rsa<5,>=3.1.4->google-auth>=1.0.1->kubernetes>=28.1.0->chromadb->-r requirements.txt (line 44)) (0.4.8)
Building wheels for collected packages: bibtexparser, free-proxy
  Building wheel for bibtexparser (setup.py): started
  Building wheel for bibtexparser (setup.py): finished with status done
  Created wheel for bibtexparser: filename=bibtexparser-1.4.3-py3-none-any.whl size=43568 sha256=51556dbda9958664baf8482735eac909205da54e6426b53242e220967a902685
  Stored in directory: /home/joebert/.cache/pip/wheels/31/9c/e2/471fa4752a2d99ddca152d75b53a2eaf38675145ba1d26ac0f
  Building wheel for free-proxy (setup.py): started
  Building wheel for free-proxy (setup.py): finished with status done
  Created wheel for free-proxy: filename=free_proxy-1.1.3-py3-none-any.whl size=6114 sha256=c4ec90a629a8e9878a9dac1b0f4ee8cc5d73385b8474fac702b2b3318a2efd51
  Stored in directory: /home/joebert/.cache/pip/wheels/95/45/0e/36fc27d383f76ec4e6f876c6584102b5ab6146ae535735a1ea
Successfully built bibtexparser free-proxy
Installing collected packages: docx2txt, xlrd, wrapt, types-python-dateutil, sphinxcontrib-serializinghtml, sphinxcontrib-qthelp, sphinxcontrib-jsmath, sphinxcontrib-htmlhelp, sphinxcontrib-devhelp, sphinxcontrib-applehelp, snowballstemmer, python-magic, pycodestyle, lxml, imagesize, fake-useragent, docutils, camel-converter, bibtexparser, babel, alabaster, sphinx, python-docx, motor, mollie-api-python, free-proxy, deprecated, arrow, sphinxcontrib-jquery, sphinx-rtd-theme, meilisearch, scholarly
Successfully installed alabaster-0.7.16 arrow-1.3.0 babel-2.17.0 bibtexparser-1.4.3 camel-converter-5.0.0 deprecated-1.2.18 docutils-0.21.2 docx2txt-0.9 fake-useragent-2.2.0 free-proxy-1.1.3 imagesize-1.4.1 lxml-6.0.2 meilisearch-0.37.0 mollie-api-python-3.9.0 motor-3.7.1 pycodestyle-2.14.0 python-docx-1.2.0 python-magic-0.4.27 scholarly-1.7.11 snowballstemmer-3.0.1 sphinx-7.3.7 sphinx-rtd-theme-3.0.2 sphinxcontrib-applehelp-2.0.0 sphinxcontrib-devhelp-2.0.0 sphinxcontrib-htmlhelp-2.1.0 sphinxcontrib-jquery-4.1 sphinxcontrib-jsmath-1.0.1 sphinxcontrib-qthelp-2.0.0 sphinxcontrib-serializinghtml-2.0.0 types-python-dateutil-2.9.0.20251008 wrapt-1.17.3 xlrd-2.0.2

## Ports Used

- **Frontend**: 8889 (Rust/ActixWeb)
- **Backend**: 8000 (Python/FastAPI)
