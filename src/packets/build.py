from datetime import datetime
import yaml
from yaml import Loader
import os.path
import re
import sys
from typing import Match, Pattern

from jinja2 import Template


class PacketDefinitionError(Exception):
    """Raise when packets.yml contains invalid information."""


def camel_to_snake(
    name: str, _re_snake: Pattern[str] = re.compile("[a-z][A-Z]")
) -> str:
    """Convert name from CamelCase to snake_case.

    Args:
        name (str): A symbol name, such as a class name.

    Returns:
        str: Name in camel case.
    """

    def repl(match: Match[str]) -> str:
        lower: str
        upper: str
        lower, upper = match.group()  # type: ignore
        return f"{lower}_{upper.lower()}"

    return _re_snake.sub(repl, name).lower()


def run():
    yml_path = os.path.join(sys.argv[1], "packets.yml")
    with open(yml_path, "rb") as packet_file:
        packets_spec = yaml.load(packet_file, Loader=Loader)
    packet_no = 0
    used_packet_nos: set[int] = set()
    for packet in packets_spec.get("packets", []):
        if "id" in packet:
            packet_no = packet["id"]
        else:
            packet_no = packet_no + 1
            packet["id"] = packet_no
        if packet_no in used_packet_nos:
            raise PacketDefinitionError(f"Duplicate packet no ({packet_no})")
        used_packet_nos.add(packet_no)
        packet["handler_name"] = camel_to_snake(packet["name"])
        packet["type"] = camel_to_snake(packet["name"]).upper()
    from rich import print

    print(packets_spec)
    compile(packets_spec)


def compile(packets_spec):
    template_path = os.path.join(sys.argv[1], "packets.py.template")
    with open(template_path, "rt") as template_file:
        template = Template(template_file.read())
    py_code = template.render(time=datetime.now().ctime(), **packets_spec)
    with open(sys.argv[2], "wt") as write_file:
        write_file.write(py_code)
    print(f"Wrote {sys.argv[2]}")


if __name__ == "__main__":
    run()
