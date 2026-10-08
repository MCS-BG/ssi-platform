#!/usr/bin/env python3
"""One-time Microsoft 365 sign-in for m365-mcp (device code flow).

Run on a trusted machine (for example the terminal laptop), never inside the repo folder output:

  python3 -m venv ~/.venvs/m365-login && ~/.venvs/m365-login/bin/pip install msal==1.39.0
  ~/.venvs/m365-login/bin/python apps/m365-mcp/login.py \
      --client-id <Application (client) ID> \
      --expected-account <your personal Microsoft account>

It prints a URL and a short code. Open the URL in any browser, enter the code, sign in with
the personal Microsoft account and approve the Microsoft Authenticator prompt, then consent
to the read-only permissions. The script then writes the MSAL token cache (it contains the
refresh token) to a file outside the repo with mode 0600 and prints the kubectl command
that loads it into the Secret m365-mcp-auth. Delete the file afterwards.

Nothing secret is printed unless you pass --print-base64.
"""
import argparse
import base64
import json
import os
import subprocess
import sys

import msal

AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["User.Read", "Mail.Read", "Calendars.Read", "Files.Read"]  # MSAL adds offline_access itself
DEFAULT_OUT = os.path.expanduser("~/.ssi/m365-token-cache.json")


def inside_git_repo(path):
    folder = os.path.dirname(os.path.abspath(path)) or "."
    while not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    try:
        out = subprocess.run(["git", "-C", folder, "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--client-id", default=os.environ.get("AZURE_CLIENT_ID"), help="Entra Application (client) ID")
    p.add_argument("--authority", default=os.environ.get("MSAL_AUTHORITY", AUTHORITY))
    p.add_argument("--expected-account", default=os.environ.get("M365_EXPECTED_ACCOUNT", ""),
                   help="refuse to save the sign-in unless it is this account")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"token cache file (default {DEFAULT_OUT})")
    p.add_argument("--namespace", default="si-lab")
    p.add_argument("--secret-name", default="m365-mcp-auth")
    p.add_argument("--print-base64", action="store_true",
                   help="also print the token cache as base64 (secret! for pasting into a Secret manifest)")
    args = p.parse_args()

    if not args.client_id:
        sys.exit("--client-id (or AZURE_CLIENT_ID) is required: the Application (client) ID of the Entra app.")
    if inside_git_repo(args.out):
        sys.exit(f"Refusing to write the token cache inside a git work tree: {args.out}")

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(args.client_id, authority=args.authority, token_cache=cache)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        sys.exit("Could not start device code sign-in: " + json.dumps(
            {k: flow.get(k) for k in ("error", "error_description")}))

    print("\n" + flow["message"], flush=True)
    print("Sign in with the personal Microsoft account; approve the Authenticator prompt if asked.\n"
          "Waiting for you to finish (the code expires in about 15 minutes)...", flush=True)
    result = app.acquire_token_by_device_flow(flow)  # blocks until done, declined or expired

    if "access_token" not in result:
        sys.exit("Sign-in did not complete: " + json.dumps(
            {k: result.get(k) for k in ("error", "error_description")}))

    who = (result.get("id_token_claims") or {}).get("preferred_username", "")
    if args.expected_account and who.lower() != args.expected_account.lower():
        sys.exit(f"Signed in as {who!r}, expected {args.expected_account!r}. Nothing was saved. "
                 "Sign out in the browser and run again with the right account.")
    granted = result.get("scope", "")
    print(f"\nSigned in as {who}. Granted scopes: {granted}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(cache.serialize())
    os.chmod(args.out, 0o600)
    print(f"Token cache written to {args.out} (mode 0600). It contains a refresh token: treat it as a password.")

    print("\nCreate or replace the Secret (run where kubectl reaches the cluster):\n")
    print(f"  kubectl -n {args.namespace} create secret generic {args.secret_name} \\\n"
          f"    --from-literal=client_id={args.client_id} \\\n"
          f"    --from-file=token_cache.json={args.out} \\\n"
          f"    --dry-run=client -o yaml | kubectl apply -f -")
    print(f"  kubectl -n {args.namespace} rollout restart deployment/m365-mcp")
    print(f"\nThen delete the local copy:  rm -P {args.out}  (Linux: shred -u {args.out})")

    if args.print_base64:
        print("\n# token_cache.json as base64 (SECRET - do not save in git or chat):")
        print(base64.b64encode(cache.serialize().encode("utf-8")).decode("ascii"))


if __name__ == "__main__":
    main()
