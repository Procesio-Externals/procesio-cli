"""connector-builder tool package marker.

The dir name has a hyphen, so this tool's own modules are imported by BARE name
(``import client``, ``from handlers import builds``) with the tool root on
sys.path at runtime — see main.py. This file just makes the folder importable
as ``tools.connector_builder`` is NOT possible (hyphen); kept for parity.
"""
