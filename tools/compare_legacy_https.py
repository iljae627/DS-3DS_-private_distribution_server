"""Run the original HTTPS implementation beside the integrated HTTP/DNS server.

Diagnostic comparison only. The integrated process must have legacy HTTPS disabled.
The selected Gen-IV file is read at startup; restart this runner after changing it.
"""
import importlib.util
import ipaddress
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location("original_dls", ROOT / "server/http_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = json.loads((ROOT / "data/state.json").read_text(encoding="utf-8"))
    offer = (ROOT / state["gen4_gift"]["path"]).resolve()
    if ROOT not in offer.parents or not offer.is_file():
        raise ValueError("Active Gen-IV file must exist inside this project")
    module.DLC_DIR = offer.parent
    module.OFFER_FILE = offer.name
    original_handle = module.handle_ssl3_client

    def local_handle(raw_client, addr, *parameters):
        if not ipaddress.ip_address(addr[0]).is_private:
            raw_client.close()
            return
        raw_client.settimeout(20)
        original_handle(raw_client, addr, *parameters)

    module.handle_ssl3_client = local_handle
    original_serve = module.serve

    def https_only(port, ssl3_parameters=None):
        if port == 443:
            original_serve(port, ssl3_parameters)

    module.serve = https_only
    print("Comparison: original HTTPS handler; integrated HTTP/DNS remain active", flush=True)
    module.main()


if __name__ == "__main__":
    main()
