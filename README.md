# Miqa Offline Test Kickoff

This GitHub Action triggers an **offline test run in Miqa**, optionally uploads outputs, and updates metadata or version overrides.

---

## 📦 Inputs

See [`action.yml`](./action.yml) for the full list of inputs.

Key inputs include:
- `MIQA_API_KEY`
- `MIQA_ENDPOINT`
- `TRIGGER_ID`
- `VERSION_NAME`
- `LOCATIONS` or `LOCATIONS_FILE`
- `OUTPUTS_ALREADY_ON_CLOUD` (true/false)
- `SET_METADATA` (optional key-values)

---

## ☁️ Example 1: Cloud-Stored Outputs (GCS/S3)

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: gh-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS: |
      sample1: gs://bucket123/run1/sample1.vcf
      sample2: s3://other-bucket/path/to/sample2.vcf
    SET_METADATA: |
      run_by: ${{ github.actor }}
      commit: ${{ github.sha }}
```

---

## 💻 Example 2: Local Outputs (to be uploaded)

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: gh-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'false'
    LOCATIONS: |
      sample1: ./outputs/sample1.vcf
      sample2: ./outputs/sample2.vcf
```

---

## 📄 Example 3: Using a CSV/YAML/JSON File for Sample Mapping

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: gh-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS_FILE: ./locations.csv
```

Supported file formats:

**YAML or JSON**
```yaml
sample1: gs://bucket/sample1.vcf
sample2: s3://bucket/sample2.vcf
```

**CSV**  
With headers:
```csv
dataset,path
sample1,gs://bucket/sample1.vcf
sample2,s3://bucket/sample2.vcf
```

Legacy-compatible:
```csv
sample,path
sample1,gs://bucket/sample1.vcf
```

Without headers:
```csv
sample1,gs://bucket/sample1.vcf
sample2,s3://bucket/sample2.vcf
```

---

## 🧪 Metadata

```yaml
SET_METADATA: |
  status: success
  initiated_by: ${{ github.actor }}
```

---

## ⚠️ Notes

- You must provide **either** `LOCATIONS` **or** `LOCATIONS_FILE`, not both.
- Cloud paths (`gs://`, `s3://`) are auto-translated to Miqa's expected format. If you are using `OUTPUTS_ALREADY_ON_CLOUD: true` and you pass a value in locations without the cloud-path prefix, it will be assumed to be the output folder and will use your default output bucket on Miqa. If you need to specify output buckets for individual datasets, pass the full cloud path. If you need to specify an output bucket override to apply to all datasets, you may pass this in `OUTPUT_BUCKET_OVERRIDE`.
- Local paths are used as-is when uploading from disk.
