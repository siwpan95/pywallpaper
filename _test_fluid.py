import sys, traceback
sys.path.insert(0, '.')
try:
    from engine.primitives import create_primitive
    from PIL import Image, ImageDraw
    config = {
        'type': 'fluid', 'grid_size': [64, 64],
        'viscosity': 0.000001, 'diffusion': 0.0001, 'force': 5.0,
        'color_map': 'ocean', 'position': {'x': 0, 'y': 0},
        'size': {'width': '100%', 'height': '100%'}
    }
    print("Creating...")
    fluid = create_primitive(config, 200, 200)
    print("Updating...")
    fluid.update(0.033, None, 0.033)
    print("Drawing...")
    img = Image.new('RGB', (200,200), (0,0,0))
    draw = ImageDraw.Draw(img)
    fluid.draw(draw)
    print("OK - saved test_fluid_out.png")
    img.save('test_fluid_out.png')
except Exception as e:
    traceback.print_exc()
