# Miqa Offline Runner (`run-miqa.py`)

`run-miqa.py` is the primary CLI tool for triggering and uploading offline tests to the Miqa QA platform. It supports:

- Triggering offline test runs
- Uploading outputs (local or cloud-based)
- Applying metadata and version overrides
- Polling for test completion
- Downloading PDF/JSON reports
- Hybrid support for Docker and native execution

---

## Basic Usage

```bash
python run-miqa.py \
  --server awstest.magnalabs.co \
  --api-key sk_test_... \
  --trigger-id cf0e8448 \
  --version-name version1 \
  --locations '{"sample1": "./outputs/sample1/"}' \
  --wait-for-completion \
  --download-reports pdf json
```

---

## 📄 Config-Driven Usage

`run-miqa.py` supports `--config` files (YAML or JSON). This lets users reuse a base configuration and override run-specific values like `--version-name`.

```bash
python run-miqa.py \
  --config config.yaml \
  --version-name run-v1
```

### Example `config.yaml`

```yaml
server: awstest.magnalabs.co
api_key: sk_test_...
trigger_id: cf0e8448
locations:
  sample1: sample1/
  sample2: sample2/output
report_folder: /reports
wait_for_completion: true
download_reports: [pdf, json]
```

---

## 🌐 Cloud vs Local Mode

`run-miqa.py` supports two modes:

### Local upload mode (default)
- Use when files are on disk (e.g., after downloading from S3/GCS)
- Relative paths (e.g., `sample1/`) are resolved to `--default-parent-path` (default: `/data`)

```yaml
outputs_already_on_cloud: false
locations:
  sample1: sample1/
```

### Cloud mode (`--outputs-already-on-cloud`)
- Use when Miqa already has access to the files via GCS/S3
- Accepts cloud URIs or dictionary syntax

```yaml
outputs_already_on_cloud: true
locations:
  sample1: gs://my-bucket/path/sample1
```

To expand relative cloud paths via env var:

```bash
export MIQA_CLOUD_PREFIX=gs://my-bucket/results/v42
```
```yaml
locations:
  sample1: sample1
```

---

## Features

- `--set-metadata` and `--get-metadata-key/value` for test annotations
- `--open-link` to automatically open the test run in a browser (not supported in CloudShell)
- `--json-output-file` to save test run metadata
- `--config` overrides everything except positional CLI args

---

## Sample Docker Command

```bash
docker run --rm \
  -v ~/miqa-inputs:/data \
  -v ~/miqa-reports:/reports \
  -v $(pwd)/config.yaml:/app/config.yaml \
  magnalabs/miqa-offline-test-kickoff \
  --config /app/config.yaml \
  --version-name version42
```

---

## 🔗 Related Tools

- [`miqa-uploader`](https://github.com/magnalabs/miqa-uploader): lightweight upload-only tool

