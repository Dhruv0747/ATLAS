from pathlib import Path
from math import sin, pi
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

theme = Path("/usr/share/plymouth/themes/atlas")
theme.mkdir(parents=True, exist_ok=True)

source = Image.open("/home/jetson/project_atlas/scripts/atlas_rover_logo_preferred.png").convert("RGBA")

for frame in range(1, 31):
    t = (frame - 1) / 30.0
    canvas = Image.new("RGBA", (700, 500), (0, 0, 0, 0))
    logo = source.copy()
    scale = 0.90 + 0.025 * sin(t * 2 * pi)
    logo.thumbnail((int(560 * scale), int(430 * scale)), Image.Resampling.LANCZOS)
    x = (canvas.width - logo.width) // 2
    y = (canvas.height - logo.height) // 2 - 12

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow.alpha_composite(logo, (x, y))
    glow = ImageEnhance.Brightness(glow).enhance(1.12).filter(ImageFilter.GaussianBlur(9))
    canvas = Image.alpha_composite(canvas, glow)
    canvas.alpha_composite(logo, (x, y))

    draw = ImageDraw.Draw(canvas, "RGBA")
    sweep_x = int(70 + t * 560)
    draw.rounded_rectangle((70, 455, 630, 463), radius=4, fill=(0, 70, 95, 170))
    draw.rounded_rectangle((70, 455, sweep_x, 463), radius=4, fill=(0, 210, 255, 235))
    draw.ellipse((sweep_x - 7, 451, sweep_x + 7, 467), fill=(130, 255, 80, 255))
    draw.text((250, 474), "BOOTING ATLAS", fill=(210, 245, 255, 230))

    canvas.save(theme / f"animation-{frame:04d}.png")

(theme / "atlas.plymouth").write_text("""[Plymouth Theme]
Name=Project ATLAS
Description=Project ATLAS rover animated boot splash
ModuleName=two-step

[two-step]
Font=Ubuntu 12
TitleFont=Ubuntu Light 30
ImageDir=/usr/share/plymouth/themes/atlas
DialogHorizontalAlignment=.5
DialogVerticalAlignment=.7
TitleHorizontalAlignment=.5
TitleVerticalAlignment=.382
HorizontalAlignment=.5
VerticalAlignment=.52
WatermarkHorizontalAlignment=.5
WatermarkVerticalAlignment=.96
Transition=none
TransitionDuration=0.0
BackgroundStartColor=0x000000
BackgroundEndColor=0x000000
ProgressBarBackgroundColor=0x003344
ProgressBarForegroundColor=0x00cfff
MessageBelowAnimation=true

[boot-up]
UseEndAnimation=false

[shutdown]
UseEndAnimation=false

[reboot]
UseEndAnimation=false

[updates]
SuppressMessages=true
ProgressBarShowPercentComplete=true
UseProgressBar=true
Title=Installing Updates...
SubTitle=Do not turn off your rover

[system-upgrade]
SuppressMessages=true
ProgressBarShowPercentComplete=true
UseProgressBar=true
Title=Upgrading ATLAS...
SubTitle=Do not turn off your rover

[firmware-upgrade]
SuppressMessages=true
ProgressBarShowPercentComplete=true
UseProgressBar=true
Title=Upgrading Firmware...
SubTitle=Do not turn off your rover

[system-reset]
SuppressMessages=true
ProgressBarShowPercentComplete=true
UseProgressBar=true
Title=Resetting ATLAS...
SubTitle=Do not turn off your rover
""")

source.thumbnail((700, 500), Image.Resampling.LANCZOS)
source.save(theme / "atlas_rover_logo_preferred.png")
