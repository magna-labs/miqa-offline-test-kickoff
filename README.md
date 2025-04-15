# Miqa Offline Test Kickoff

This GitHub Action triggers an **offline test run in Miqa**, optionally uploads outputs, and updates metadata or version overrides.

---

## Inputs

See [`action.yml`](./action.yml) for the full list of inputs.

Key inputs include:
- `MIQA_API_KEY`
- `MIQA_ENDPOINT`
- `TRIGGER_ID`
- `VERSION_NAME`
- `LOCATIONS` or `LOCATIONS_FILE`
- `OUTPUTS_ALREADY_ON_CLOUD` (true/false)

---

## ☁️ Example 1: Cloud-Stored Outputs (GCS/S3)

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1.1
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: gh-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS: |
      sample1: gs://bucket123/run1/sample1.vcf
      sample2: s3://other-bucket/path/to/sample2.vcf
```

---

## 💻 Example 2: Local Outputs (to be uploaded)

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1.1
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
- uses: magna-labs/miqa-offline-test-kickoff@v1.1
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
sample1: gs://bucket/folder1/
sample2: s3://bucket/folder2/
```

**CSV**  
With headers:
```csv
dataset,path
sample1,gs://bucket/folder1/
sample2,s3://bucket/folder2/
```

Without headers:
```csv
sample1,gs://bucket/folder1/
sample2,s3://bucket/folder2/
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
- Cloud paths (`gs://`, `s3://`) are auto-translated to Miqa's expected format.
- Local paths are used as-is when uploading from disk.


---

## 📦 Optional: OUTPUT_BUCKET_OVERRIDE

If you are using `OUTPUTS_ALREADY_ON_CLOUD: true` and pass values in `LOCATIONS` that are not full `gs://` or `s3://` paths (e.g. just folders), Miqa will use its **default bucket**.

To override this bucket across **all** samples, use the optional `OUTPUT_BUCKET_OVERRIDE`:

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1.0
  with:
    ...
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS: |
      sample1: run-outputs
      sample2: run-outputs2/sample2.vcf
    OUTPUT_BUCKET_OVERRIDE: my-custom-bucket
```

This will be translated into:
```json
{
  "sample1": { "output_bucket": "my-custom-bucket", "output_folder": "run-outputs" },
  "sample2": { "output_bucket": "my-custom-bucket", "output_folder": "run-outputs2", "output_file_prefix": "sample2.vcf" }
}
```

If you want per-sample output buckets, pass full `gs://` or `s3://` paths directly.


---

## 📄 Example 4: Fully Split File Locations in CSV

You can also pass a CSV file that includes `output_folder`, `output_bucket`, and `output_file_prefix` explicitly:

```csv
name,output_folder,output_bucket,output_file_prefix
sample1,results/sample1s,my-bucket,sample1.vcf
sample2,results/sample2s,other-bucket,sample2.bam
```

Use it like:

```yaml
- uses: magna-labs/miqa-offline-test-kickoff@v1
  with:
    MIQA_API_KEY: ${{ secrets.MIQA_API_KEY }}
    MIQA_ENDPOINT: yourco.miqa.io
    TRIGGER_ID: my-trigger-id
    VERSION_NAME: run-${{ github.sha }}
    OUTPUTS_ALREADY_ON_CLOUD: 'true'
    LOCATIONS_FILE: ./split_output_locations.csv
```

This is especially useful if you want fine-grained control over bucket, folder, and filename separately for each sample.

