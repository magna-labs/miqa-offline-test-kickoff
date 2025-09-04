import argparse
import requests
import json
import sys
import yaml
import os
import re
import csv
import time
from miqatools.remoteexecution.triggertest_helpers import get_trigger_info
from miqatools.remoteexecution.triggertestandupload_python import (
    trigger_test_and_upload_by_dsid,
    upload_to_test_by_dsid,
)

def normalize_miqa_endpoint(endpoint):
    endpoint = endpoint.replace("https://", "").replace("http://", "")
    if endpoint.endswith("/api"):
        endpoint = endpoint[:-4]
    return endpoint.rstrip("/")

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

def build_locations_from_parent_dir(parent: str, ds_id_mapping: dict, is_cloud: bool):
    """
    Return a dict {sample_name: location} by joining parent/<sample_name>.
    For cloud: returns "s3://.../parent/<sample_name>" (or gs://...).
    For local: returns os.path.join(parent, sample_name).
    """
    results = {}
    if is_cloud:
        # Expect parent like "s3://bucket/prefix" or "gs://bucket/prefix"
        if not (parent.startswith("s3://") or parent.startswith("gs://")):
            raise ValueError(f"Expected cloud parent to start with s3:// or gs://, got: {parent}")
        scheme, rest = parent.split("://", 1)
        bucket, *prefix_parts = rest.split("/", 1)
        prefix = prefix_parts[0] if prefix_parts else ""
        for sample_name in ds_id_mapping.keys():
            child_prefix = f"{prefix.rstrip('/')}/{sample_name}" if prefix else sample_name
            results[sample_name] = f"{scheme}://{bucket}/{child_prefix}"
    else:
        for sample_name in ds_id_mapping.keys():
            results[sample_name] = os.path.join(parent, sample_name)
    return results

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
                    if "output_folder" in row:
                        mapping[name] = {
                            "output_folder": row["output_folder"],
                            "output_bucket": row.get("output_bucket"),
                            "output_file_prefix": row.get("output_file_prefix"),
                        }
                        mapping[name] = {k: v for k, v in mapping[name].items() if v}
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
    cloud_prefix = os.getenv("MIQA_CLOUD_PREFIX")
    if isinstance(location_value, dict):
        return location_value
    if isinstance(location_value, str):
        if cloud_prefix and not location_value.startswith("gs://") and not location_value.startswith("s3://"):
            location_value = cloud_prefix.rstrip("/") + "/" + location_value.lstrip("/")
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

def trigger_offline_test_and_get_run_info(
    miqa_server,
    trigger_id,
    version_name,
    headers,
    local,
    ds_id_overrides=None,
    app_name="mn",
    additional_query_params="",
    raise_if_multi_execs=False,
    debug=False,
):
    url = f"https://{miqa_server}/api/test_trigger/{trigger_id}/{'execute_and_set_details' if not local else 'execute'}"
    query = f"?app={app_name}&name={version_name}&offline_version=1&skip_check_docker=1&is_non_docker=1&raise_if_multi_execs={raise_if_multi_execs}"

    if additional_query_params and debug:
        print(f"🧪 Raw additional_query_params: [{additional_query_params}]")
        print("🧪 Hexdump of additional_query_params:")
        print("    " + " ".join(f"{ord(c):02x}" for c in additional_query_params))
        query += additional_query_params

    url += query
    if debug:
        print(f"🧪 Final URL being called:\n{url}")

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

def poll_for_completion(run_id, miqa_server, headers, max_checks, frequency_seconds):
    status_url = f"https://{miqa_server}/api/test_chain_run/{run_id}/get_status"
    for attempt in range(1, max_checks + 1):
        response = requests.get(status_url, headers=headers)
        try:
            json_res = response.json()
        except Exception as e:
            print(f"⚠️ Failed to parse response on attempt {attempt}: {e}")
            continue

        print(f"[Attempt {attempt}] Status:")
        print(json.dumps(json_res, indent=2))

        status = json_res.get("data", {}).get("status")
        if status == "done":
            print(f"✅ Miqa run {run_id} completed.")
            print(f"📊 Outcome: {json_res.get('data', {}).get('outcome')}")
            print(f"🔗 Link: {json_res.get('data', {}).get('link')}")
            return True
        if attempt < max_checks:
            time.sleep(frequency_seconds)
    print(f"⏳ Reached max attempts ({max_checks}) without completion.")
    return False

import os

def download_report(run_id, report_type, output_folder, miqa_server, headers):
    report_url = f"https://{miqa_server}/api/test_chain_run/{run_id}/{report_type}"
    report_path = os.path.join(output_folder, f"Miqa_Test_Report_{run_id}.{report_type}")

    # ✅ Ensure the folder exists
    os.makedirs(output_folder, exist_ok=True)

    response = requests.get(report_url, headers=headers)
    if response.ok:
        with open(report_path, "wb") as f:
            f.write(response.content)
        print(f"📥 Report saved to {report_path}")
    else:
        print(f"❌ Failed to download {report_type.upper()} report from {report_url}. Status: {response.status_code}")

def log_effective_config_with_paths(args, ds_id_mapping, locations_lookup_by_sid):
    from rich.console import Console
    from rich.table import Table
    console = Console()
    table = Table(title="📋 Effective Miqa Parameters", show_lines=True)

    table.add_column("Parameter", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    display_items = {
        "Server": args.server,
        "Trigger ID": args.trigger_id,
        "Version Name": args.version_name,
        "Outputs on Cloud": str(args.outputs_already_on_cloud),
        "Report Folder": args.report_folder,
        "Wait for Completion": str(args.wait_for_completion),
        "Download Reports": ", ".join(args.download_reports or []),
    }

    for key, val in display_items.items():
        table.add_row(key, str(val))

    table.add_row("Resolved Paths", "")
    reverse_sid_map = {v: k for k, v in ds_id_mapping.items()}

    for sid, resolved in locations_lookup_by_sid.items():
        sample_name = reverse_sid_map.get(sid, "(unknown)")
        resolved_str = json.dumps(resolved, indent=2) if isinstance(resolved, dict) else str(resolved)
        table.add_row(f"  {sample_name} ({sid})", resolved_str)

    console.print(table)

def main():
    # Step 1: Parse --config if provided
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=str)
    config_args, remaining_argv = config_parser.parse_known_args()
    
    defaults = {}
    if config_args.config:
        with open(config_args.config) as f:
            defaults = yaml.safe_load(f) if config_args.config.endswith((".yaml", ".yml")) else json.load(f)
    
    # Step 2: Use env vars for fallback if not in config
    for key in ["server", "api_key", "trigger_id", "version_name", "locations", "report_folder", "output_parent_folder"]:
        val = os.getenv(f"MIQA_{key.upper()}")
        if val and key not in defaults:
            defaults[key] = val
    
    if "report_folder" not in defaults:
        defaults["report_folder"] = "."


    # Step 3: Parse the rest of the args
    parser = argparse.ArgumentParser(description="CLI tool to trigger MIQA tests, upload data, and update metadata.", parents=[config_parser])
    parser.set_defaults(**defaults)
    parser.add_argument("--server", type=str, required="server" not in defaults)
    parser.add_argument("--api-key", type=str, required="api_key" not in defaults)
    parser.add_argument("--trigger-id", type=str, required="trigger_id" not in defaults)
    parser.add_argument("--version-name", type=str, required="version_name" not in defaults)
    parser.add_argument("--outputs-already-on-cloud", action='store_true')
    parser.add_argument("--get-metadata-key", type=str, required=False)
    parser.add_argument("--get-metadata-value", type=str, required=False)
    parser.add_argument("--set-metadata", type=str, required=False)
    parser.add_argument("--locations", type=str, required=False)
    parser.add_argument("--locations-file", type=str, required=False)
    parser.add_argument("--output-bucket-override", type=str, required=False)
    parser.add_argument("--json-output-file", type=str, required=False, help="Optional path to write JSON summary")
    parser.add_argument("--app-name", type=str, required=False, default="mn", help="App name to include in the trigger call (e.g. 'mn' or 'gh')")
    parser.add_argument("--additional-query-params", type=str, required=False, default="", help="Extra query string (e.g. '&repo=foo&commit=sha')")
    parser.add_argument("--wait-for-completion", action="store_true", help="Poll Miqa until the test run is complete")
    parser.add_argument("--poll-frequency", type=int, default=60, help="Seconds between poll attempts")
    parser.add_argument("--poll-max-attempts", type=int, default=20, help="Maximum polling attempts")
    parser.add_argument("--download-reports", type=str, nargs="+", help="One or more report types to download after successful completion (e.g. 'pdf', 'json')")
    parser.add_argument("--report-folder", type=str, help="Where to save downloaded reports")
    parser.add_argument("--default-parent-path", type=str, default="/data", help="Where to save downloaded reports")    
    parser.add_argument('--open-link', action='store_true', help="Open the test run link immediately.")
    parser.add_argument('--strict', action='store_true', help="Fail if paths or samples are invalid")
    parser.add_argument("--output-parent-folder", type=str, help="Prefix to prepend to each output_folder when uploading or specifying cloud locations")
    parser.add_argument(
        "--docker-mode",
        action="store_true",
        help="Resolve relative paths under the default parent (e.g. /data). Used inside Docker containers."
    )
    parser.add_argument("--raise-if-multi-execs", action='store_true')
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args(remaining_argv)
    headers = {"content-type": "application/json", "app-key": args.api_key, "app_key": args.api_key}
    miqa_server = normalize_miqa_endpoint(args.server)

    if not args.locations and not args.locations_file:
        raise Exception("You must provide either --locations or --locations-file.")
    if args.locations and args.locations_file:
        raise Exception("Please provide only one of --locations or --locations-file (not both).")
    if args.locations_file and not os.path.exists(args.locations_file):
        raise FileNotFoundError(f"Locations file not found: {args.locations_file}")

    if args.locations_file:
        locations_lookup_by_samplename = load_locations_from_file(args.locations_file)
    else:
        if isinstance(args.locations, str):
            locations_raw = interpolate_env_variables(args.locations)
            parsed = parse_yaml_or_json(locations_raw)

            # If the parsed value is a string, treat it as a parent directory and auto-expand.
            if isinstance(parsed, str):
                # We need ds_id_mapping to know the expected dataset names.
                response = get_trigger_info(miqa_server, args.trigger_id)
                if not isinstance(response, dict):
                    raise Exception("Failed to retrieve dataset ID mapping.")
                ds_id_mapping = response.get("ds_id_mapping", {}).get("results", {}).get("data", {})
                if not ds_id_mapping:
                    raise RuntimeError("Could not resolve dataset names for auto-mapping from parent directory.")

                locations_lookup_by_samplename = build_locations_from_parent_dir(
                    parsed,
                    ds_id_mapping,
                    args.outputs_already_on_cloud
                )
            elif isinstance(parsed, dict):
                locations_lookup_by_samplename = parsed
            else:
                raise ValueError("--locations must be a mapping or a parent directory string")
        else:
            locations_lookup_by_samplename = args.locations

    set_metadata_raw = interpolate_env_variables(args.set_metadata or "")
    set_metadata_dict = parse_yaml_or_json(set_metadata_raw) if args.set_metadata else None

    response = get_trigger_info(miqa_server, args.trigger_id)
    if not isinstance(response, dict):
        raise Exception("Failed to retrieve dataset ID mapping.")
    ds_id_mapping = response.get("ds_id_mapping", {}).get("results", {}).get("data", {})

    passed_names_not_in_mapping = False
    locations_lookup_by_sid = {}
    for sample_name, location_value in locations_lookup_by_samplename.items():
        sid = ds_id_mapping.get(sample_name)
        if not sid:
            passed_names_not_in_mapping = True
            if args.strict:
                raise ValueError(f"❌ Strict mode: sample '{sample_name}' not found in trigger mapping.")
            continue

        if not args.outputs_already_on_cloud:
            if isinstance(location_value, str) and not os.path.isabs(location_value):
                if args.docker_mode:
                    location_value = os.path.join(args.default_parent_path, location_value)
                else:
                    location_value = os.path.abspath(location_value)
        
            if isinstance(location_value, str) and not os.path.exists(location_value):
                msg = f"Path does not exist for sample '{sample_name}': {location_value}"
                if args.strict:
                    raise FileNotFoundError(f"❌ Strict mode: {msg}")
                else:
                    print(f"⚠️ {msg}")

        if args.outputs_already_on_cloud:
            parsed = convert_location_for_cloud(location_value)
            if args.output_bucket_override and isinstance(parsed, dict) and "output_bucket" not in parsed:
                parsed["output_bucket"] = args.output_bucket_override
            # Apply output_parent_folder prefix if needed
            if args.output_parent_folder and isinstance(parsed, dict) and "output_folder" in parsed:
                parsed["output_folder"] = os.path.join(args.output_parent_folder.rstrip("/"), parsed["output_folder"].lstrip("/"))

            locations_lookup_by_sid[sid] = parsed
        else:
            if not os.path.isabs(location_value):
                location_value = os.path.join(args.default_parent_path, location_value)
            locations_lookup_by_sid[sid] = location_value


    log_effective_config_with_paths(args, ds_id_mapping, locations_lookup_by_sid)

    if args.strict and not locations_lookup_by_sid:
        raise RuntimeError("❌ Strict mode: No valid sample paths were resolved. Aborting.")


    run_info = trigger_offline_test_and_get_run_info(
        miqa_server,
        args.trigger_id,
        args.version_name,
        headers,
        not args.outputs_already_on_cloud,
        locations_lookup_by_sid,
        app_name=args.app_name,
        additional_query_params=args.additional_query_params,
        raise_if_multi_execs=args.raise_if_multi_execs,
        debug=args.debug,
    )
    run_id = run_info.get("run_id")

    if not args.outputs_already_on_cloud:
        for dsid, path in locations_lookup_by_sid.items():
            if isinstance(path, str) and os.path.isfile(path):
                folder = os.path.dirname(path) or "."
                filename = os.path.basename(path)
                print(f"Uploading single file {filename} from folder {folder} for dataset {dsid}")
                upload_to_test_by_dsid(
                    run_id,
                    miqa_server,
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
                    miqa_server,
                    {dsid: path},
                    filepatterns=None,
                    quiet=False,
                    api_key=args.api_key,
                    detailed_file_logs=True,
                )

    if set_metadata_dict:
        update_metadata(set_metadata_dict, miqa_server, run_id, headers)

    if args.get_metadata_key:
        latest_tcr_matching_metadata = get_latest_tcr_matching_metadata(
            miqa_server, headers, run_id, args.get_metadata_key, args.get_metadata_value
        )
        print(f"Latest matching TCR is {latest_tcr_matching_metadata}")
        set_version_overrides({"-1": latest_tcr_matching_metadata}, miqa_server, run_id, headers)

    poll_successful = True
    if args.wait_for_completion:
        print("⏳ Polling for completion...")
        poll_successful = poll_for_completion(run_id, miqa_server, headers, args.poll_max_attempts, args.poll_frequency)

    if poll_successful and args.download_reports:
        for report_type in args.download_reports:
            download_report(run_id, report_type, args.report_folder, miqa_server, headers)
    elif args.download_reports and not poll_successful:
        print("⚠️ Skipping report download because test did not complete successfully.")

    print("\n✅ Miqa Test Chain Run Info:")
    print(json.dumps(run_info, indent=2))
    
    # Warn if no valid samples matched
    if len(locations_lookup_by_sid) == 0 and passed_names_not_in_mapping:
        print(
            "⚠️ None of the sample names you provided match this test trigger.\n"
            "   Please check your sample names.\n"
            f"   Available sample names: {', '.join(ds_id_mapping.keys())}"
        )
        
    expected_sample_count = len(ds_id_mapping)
    provided_sample_count = len(locations_lookup_by_sid)
    
    if provided_sample_count == 0:
        print("⚠️ No files were uploaded for this run.")
    elif provided_sample_count < expected_sample_count:
        print(
            f"⚠️ Only {provided_sample_count} of {expected_sample_count} expected samples were uploaded."
        )
    
    grid_upload_url = run_info.get("details", {}).get("links", {}).get("grid_upload")
    if grid_upload_url:
        print("📥 You can manually upload missing files here:")
        print(f"   {grid_upload_url}")

    if args.json_output_file:
        with open(args.json_output_file, "w") as f:
            json.dump(run_info, f)

    link = run_info.get("link")
    if link:
        print("\n🔗 Open the test run here:")
        print(link)

        # If the user specified to open the link, do it
        if args.open_link:
            try:
                import webbrowser
                print("Opening the link now...")
                webbrowser.open(link)
            except Exception as e:
                print(f"⚠️ Could not open browser: {e}")


if __name__ == "__main__":
    main()
