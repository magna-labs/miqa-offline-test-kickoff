# Miqa Offline

Trigger **offline test runs in Miqa**, upload local/cloud outputs, update metadata, and download reports.

This repository provides:

* A **CLI** (`miqa-offline`) published to PyPI
* A **Docker image** (`magnalabs/miqa-offline-test-kickoff`)
* A **GitHub Action** for use in CI/CD workflows

---

## 🚀 CLI (PyPI)

Install with [pipx](https://pypa.github.io/pipx/) (recommended):

```bash
pipx install miqa-offline
miqa-offline --help
```

Or run without installing (using [uvx](https://github.com/astral-sh/uv)):

```bash
uvx miqa-offline --help
```

Example:

```bash
miqa-offline \
  --server yourco.miqa.io \
  --api-key $MIQA_API_KEY \
  --trigger-id my-trigger-id \
  --version-name "local-test" \
  --locations-file ./locations.yaml \
  --wait-for-completion \
  --download-reports pdf json
```

---

## 🐳 Docker

We publish an image to Docker Hub under `magnalabs/miqa-offline-test-kickoff`.

Mount your data/config and run:

```bash
docker run --rm \
  -v $(pwd)/data:/data \
  -v $(pwd)/reports:/reports \
  -v $(pwd)/config.yaml:/app/config.yaml \
  magnalabs/miqa-offline-test-kickoff:latest \
  --config /app/config.yaml \
  --docker-mode \
  --version-name my-test-run --open-link
```

* `--docker-mode` makes relative paths resolve under `/data`, matching the `-v $(pwd)/data:/data` mount.
* Reports will be written to `$(pwd)/reports`.

---

## 🤖 GitHub Action

You can also call this as a GitHub Action in workflows.

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1.7.0
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: gh-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS_FILE: ./locations.yaml
```

Inputs include:

* `MIQA_API_KEY`
* `MIQA_ENDPOINT`
* `TRIGGER_ID`
* `VERSION_NAME`
* `LOCATIONS` or `LOCATIONS_FILE`
* `OUTPUTS_ALREADY_ON_CLOUD`
* `OUTPUT_BUCKET_OVERRIDE`
* `SET_METADATA`

See [`action.yml`](./action.yml) for the full list.

---

## 📄 Input Formats

**YAML or JSON**

```yaml
sample1: gs://bucket/folder1/
sample2: s3://bucket/folder2/
```

**CSV with headers**

```csv
dataset,path
sample1,gs://bucket/folder1/
sample2,s3://bucket/folder2/
```

**CSV without headers**

```csv
sample1,gs://bucket/folder1/
sample2,s3://bucket/folder2/
```

**CSV with split fields**

```csv
name,output_folder,output_bucket,output_file_prefix
sample1,results/sample1s,my-bucket,sample1.vcf
sample2,results/sample2s,other-bucket,sample2.bam
```

Usage in workflow:

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1.7.0
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: run-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS_FILE: ./split_output_locations.csv
```

---

## ⚠️ Notes

* Provide **either** `LOCATIONS` or `LOCATIONS_FILE`, not both.
* Cloud paths (`gs://`, `s3://`) are auto-translated to Miqa's expected format.
* Local paths are used as-is when uploading from disk.
* `OUTPUT_BUCKET_OVERRIDE` lets you override the default bucket for all samples.
