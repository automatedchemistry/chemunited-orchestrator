from __future__ import annotations

from chemunited.qt.project.storage import load_draw, save_draw


def test_save_draw_writes_python_setup(tmp_path):
    save_draw(
        tmp_path,
        {
            "components": [
                {
                    "name": "PumpA",
                    "figure": "HPLCPump",
                    "position": [1.0, 2.0],
                    "angle": 0,
                }
            ],
            "connections": [
                {
                    "origin": "PumpA",
                    "destination": "ReactorA",
                    "origin_port": 2,
                    "destination_port": 1,
                    "length": "100 mm",
                }
            ],
        },
    )

    setup_path = tmp_path / "draw" / "setup.py"
    content = setup_path.read_text(encoding="utf-8")

    assert setup_path.exists()
    assert "def build_draw(platform):" in content
    assert "platform.add_component(" in content
    assert "position=(1.0, 2.0)" in content
    assert "platform.add_connection(" in content
    assert "destiny='ReactorA'" in content
    assert "destiny_port=1" in content


def test_load_draw_executes_python_setup(tmp_path):
    setup_path = tmp_path / "draw" / "setup.py"
    setup_path.parent.mkdir(parents=True)
    setup_path.write_text(
        """
def build_draw(platform):
    for name, x in [('PumpA', 0.0), ('PumpB', 100.0)]:
        platform.add_component(
            name=name,
            figure='HPLCPump',
            position=(x, 0.0),
            angle=0,
        )

    platform.add_connection(
        origin='PumpA',
        destiny='PumpB',
        origin_port=2,
        destiny_port=1,
        diameter='1 mm',
    )
""".lstrip(),
        encoding="utf-8",
    )

    assert load_draw(tmp_path) == {
        "components": [
            {
                "name": "PumpA",
                "figure": "HPLCPump",
                "position": (0.0, 0.0),
                "angle": 0,
            },
            {
                "name": "PumpB",
                "figure": "HPLCPump",
                "position": (100.0, 0.0),
                "angle": 0,
            },
        ],
        "connections": [
            {
                "origin": "PumpA",
                "destination": "PumpB",
                "origin_port": 2,
                "destination_port": 1,
                "diameter": "1 mm",
            }
        ],
    }


def test_load_draw_returns_empty_payload_when_setup_is_missing(tmp_path):
    assert load_draw(tmp_path) == {"components": [], "connections": [], "canvas": {}}
