"""Tests for the CLI argument parser.

Covers:
- --tray defaults to False
- --tray flag is parsed correctly
"""

from __future__ import annotations

from chemunited_sim.cli.main import build_parser


def test_tray_flag_defaults_to_false():
    args = build_parser().parse_args([])
    assert args.tray is False


def test_tray_flag_parsed():
    args = build_parser().parse_args(["--tray"])
    assert args.tray is True
