import subprocess

SRC = "simulation_dashboard.mp4"
DST = "_static/simulation_dashboard.gif"
PALETTE = "_static/.simulation_dashboard_palette.png"
FILTERS = "fps=10,scale=700:-1:flags=lanczos"

if __name__ == "__main__":
    # Two-pass palette encode: much smaller and higher quality than a naive
    # frame-by-frame GIF writer (e.g. moviepy's default write_gif).
    subprocess.run(
        ["ffmpeg", "-y", "-i", SRC, "-vf", f"{FILTERS},palettegen", PALETTE],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            SRC,
            "-i",
            PALETTE,
            "-filter_complex",
            f"{FILTERS}[x];[x][1:v]paletteuse",
            DST,
        ],
        check=True,
    )
