import argparse
import requests
import json
import sys
import yaml
import os
import re
import csv
from miqatools.remoteexecution.triggertest_helpers import get_trigger_info
from miqatools.remoteexecution.triggertestandupload_python import (
    trigger_test_and_upload_by_dsid,
    upload_to_test_by_dsid,
)

def interpolate_env_variables(raw_string):
    pattern = re.compile(r'\$\{\{\s*([\w\.]+)\s*\}\}|\$\{([\w\.]+)\}')
    def replace_var(match):
        var_name = match.group(1) or match.group(2)
        return os.environ.get(var_name, match.group(0))
    return pattern.sub(replace_var, raw_string)

def parse_yaml_or_json(string_input):
    try:
        return json.loads(string_input)
    except json.JSONDecodeError:
        return yaml.safe_load(string_input)

def load_locations_from_file(path):
    if path.endswith(".yaml") or path.endswith(".yml"):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    elif path.endswith(".json"):
        with open(path, "r") as f:
            return json.load(f)
    elif path.endswith(".csv"):
        mapping = {}
        with open(path, newline="") as f:
            try:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("dataset") or row.get("sample") or row.get("name")
                    if not name:
                        raise ValueError("Missing dataset/sample/name column.")

                    # Full-field format
                    if "output_folder" in row:
                        mapping[name] = {
                            "output_folder": row["output_folder"],
                            "output_bucket": row.get("output_bucket"),
                            "output_file_prefix": row.get("output_file_prefix"),
                        }
                        mapping[name] = {k: v for k, v in mapping[name].items() if v}
                    # Legacy path-based format
                    elif "path" in row:
                        mapping[name] = row["path"]
                    else:
                        raise ValueError("CSV must have either 'path' or 'output_folder'.")
            except Exception:
                f.seek(0)
                reader = csv.reader(f)
                for row in reader:
                    if len(row) != 2:
                        raise ValueError("CSV rows must have exactly two values: dataset,path")
                    mapping[row[0]] = row[1]
        return mapping
    else:
        raise ValueError(f"Unsupported file format: {path}")

def convert_location_for_cloud(location_value):
    if isinstance(location_value, dict):
        return location_value
    if isinstance(location_value, str):
        if location_value.startswith("gs://") or location_value.startswith("s3://"):
            scheme, rest = location_value.split("://", 1)
            parts = rest.split("/", 1)
            if len(parts) == 2:
                bucket = parts[0]
                full_path = parts[1]
                path_parts = full_path.rsplit("/", 1)
                if len(path_parts) == 2 and "." in path_parts[1]:
                    return {
                        "output_bucket": bucket,
                        "output_folder": path_parts[0],
                        "output_file_prefix": path_parts[1]
                    }
                return {
                    "output_bucket": bucket,
                    "output_folder": full_path
                }
        return {"output_folder": location_value}
    raise ValueError(f"Unrecognized location format: {location_value}")

def trigger_offline_test_and_get_run_info(miqa_server, trigger_id, version_name, headers, local, ds_id_overrides=None):
    url = f"https://{miqa_server}/api/test_trigger/{trigger_id}/{'execute_and_set_details' if not local else 'execute'}?app=mn&name={version_name}&offline_version=1&skip_check_docker=1&is_non_docker=1"
    body = ds_id_overrides if not local else {}
    print(f"Triggering offline test with body: {json.dumps(body, indent=2)}")
    response = requests.post(url, json=body, headers=headers)
    if response.ok:
        return response.json()
    else:
        print(f"Error: {response.text}")
        raise Exception(f"Failed to kick off the run at url '{url}'")

def update_metadata(metadata, miqa_server, run_id, headers):
    update_metadata_url = f"https://{miqa_server}/api/test_chain_run/{run_id}/set_trigger_info"
    response = requests.post(update_metadata_url, json=metadata, headers=headers)
    if response.ok:
        return response.json()
    else:
        print(f"Error: {response.text}")
        raise Exception(f"Failed to update metadata for {run_id}")

def get_latest_tcr_matching_metadata(miqa_server, headers, run_id, metadata_key, metadata_value):
    url = f"https://{miqa_server}/api/test_chain_run/{run_id}/get_latest_for_metadata?metadata_key={metadata_key}&metadata_value={metadata_value}"
    response = requests.get(url, headers=headers)
    if response.ok:
        return response.json().get("tcr_id")
    else:
        print(f"Error: {response.text}", file=sys.stderr)
        sys.exit(1)

def set_version_overrides(overrides_lookup, miqa_server, run_id, headers):
    update_metadata_url = f"https://{miqa_server}/api/test_chain_run/{run_id}/set_version_overrides"
    response = requests.post(update_metadata_url, json=overrides_lookup, headers=headers)
    if response.ok:
        return response.json()
    else:
        print(f"Error: {response.text}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="CLI tool to trigger MIQA tests, upload data, and update metadata.")
    parser.add_argument("--server", type=str, required=True)
    parser.add_argument("--api-key", type=str, required=True)
    parser.add_argument("--trigger-id", type=str, required=True)
    parser.add_argument("--version-name", type=str, required=True)
    parser.add_argument("--outputs-already-on-cloud", action='store_true')
    parser.add_argument("--get-metadata-key", type=str, required=False)
    parser.add_argument("--get-metadata-value", type=str, required=False)
    parser.add_argument("--set-metadata", type=str, required=False)
    parser.add_argument("--locations", type=str, required=False)
    parser.add_argument("--locations-file", type=str, required=False)
    parser.add_argument("--output-bucket-override", type=str, required=False)

    args = parser.parse_args()
    headers = {"content-type": "application/json", "app-key": args.api_key}

    if not args.locations and not args.locations_file:
        raise Exception("You must provide either --locations or --locations-file.")
    if args.locations and args.locations_file:
        raise Exception("Please provide only one of --locations or --locations-file (not both).")
    if args.locations_file and not os.path.exists(args.locations_file):
        raise FileNotFoundError(f"Locations file not found: {args.locations_file}")

    if args.locations_file:
        locations_lookup_by_samplename = load_locations_from_file(args.locations_file)
    else:
        locations_raw = interpolate_env_variables(args.locations)
        locations_lookup_by_samplename = parse_yaml_or_json(locations_raw)

    set_metadata_raw = interpolate_env_variables(args.set_metadata or "")
    set_metadata_dict = parse_yaml_or_json(set_metadata_raw) if args.set_metadata else None

    response = get_trigger_info(args.server, args.trigger_id)
    if not isinstance(response, dict):
        raise Exception("Failed to retrieve dataset ID mapping.")
    ds_id_mapping = response.get("ds_id_mapping", {}).get("results", {}).get("data", {})

    locations_lookup_by_sid = {}
    for sample_name, location_value in locations_lookup_by_samplename.items():
        sid = ds_id_mapping.get(sample_name)
        if not sid:
            continue
        if args.outputs_already_on_cloud:
            parsed = convert_location_for_cloud(location_value)
            if args.output_bucket_override and isinstance(parsed, dict) and "output_bucket" not in parsed:
                parsed["output_bucket"] = args.output_bucket_override
            locations_lookup_by_sid[sid] = parsed
        else:
            locations_lookup_by_sid[sid] = location_value

    run_info = trigger_offline_test_and_get_run_info(
        args.server,
        args.trigger_id,
        args.version_name,
        headers,
        not args.outputs_already_on_cloud,
        locations_lookup_by_sid,
    )
    run_id = run_info.get("run_id")

    if not args.outputs_already_on_cloud:
        for dsid, path in locations_lookup_by_sid.items():
            if isinstance(path, str) and os.path.isfile(path):
                folder = os.path.dirname(path) or "."
                filename = os.path.basename(path)
                upload_to_test_by_dsid(
                    run_id,
                    args.server,
                    {dsid: folder},
                    filepatterns=None,
                    filepattern_end=filename,
                    quiet=False,
                    api_key=args.api_key,
                    detailed_file_logs=True,
                )
            else:
                upload_to_test_by_dsid(
                    run_id,
                    args.server,
                    {dsid: path},
                    filepatterns=None,
                    quiet=False,
                    api_key=args.api_key,
                    detailed_file_logs=True,
                )

    if set_metadata_dict:
        update_metadata(set_metadata_dict, args.server, run_id, headers)

    if args.get_metadata_key:
        latest_tcr_matching_metadata = get_latest_tcr_matching_metadata(
            args.server, headers, run_id, args.get_metadata_key, args.get_metadata_value
        )
        print(f"Latest matching TCR is {latest_tcr_matching_metadata}")
        set_version_overrides({"-1": latest_tcr_matching_metadata}, args.server, run_id, headers)

if __name__ == "__main__":
    main()
