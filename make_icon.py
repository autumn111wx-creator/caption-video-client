from PIL import Image, ImageDraw

sizes = (16, 24, 32, 48, 64, 128, 256)
image = Image.new("RGBA", (256, 256), (13, 23, 40, 255))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((12, 12, 244, 244), radius=58, fill=(44, 100, 235, 255))
draw.polygon([(78, 57), (199, 128), (78, 199)], fill=(255, 255, 255, 255))
draw.rounded_rectangle((52, 211, 204, 226), radius=7, fill=(71, 220, 174, 255))
image.save("app.ico", sizes=[(size, size) for size in sizes])
