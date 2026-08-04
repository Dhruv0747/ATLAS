from PIL import Image, ImageFilter

src = Image.open("/home/jetson/project_atlas/scripts/atlas_boot_logo.png").convert("RGBA")
bg = Image.new("RGB", (1024, 600), (2, 5, 10))

logo = src.copy()
logo.thumbnail((620, 420), Image.Resampling.LANCZOS)
x = (1024 - logo.width) // 2
y = (600 - logo.height) // 2

layer = Image.new("RGBA", (1024, 600), (0, 0, 0, 0))
layer.alpha_composite(logo, (x, y))
glow = layer.filter(ImageFilter.GaussianBlur(18))

out = Image.alpha_composite(bg.convert("RGBA"), glow)
sharp = Image.new("RGBA", (1024, 600), (0, 0, 0, 0))
sharp.alpha_composite(logo, (x, y))
out = Image.alpha_composite(out, sharp).convert("RGB")
out.save("/home/jetson/Pictures/project_atlas_wallpaper.png")
