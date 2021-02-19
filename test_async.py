import asyncio
import time
import web_camera
from utils import get_conf


async def get_answer():
    c = web_camera.Cameras()
    try:
        while True:
            print('get answer')
            await c.wait_cam_loop()

    except KeyboardInterrupt:
        pass

async def run():
    while True:
        print('running my job')
        await asyncio.sleep(1)


asyncio.run(get_answer())

await asyncio.gather(get_answer(), run())

async def main():
    t1 = asyncio.create_task(get_answer())
    t2 = asyncio.create_task(run())
    await t1
    await t2

asyncio.run(main())

camera = None

async def get_cam():
    async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
        await ws.send(json.dumps({'key': get_conf('key'), 'force': True}))
        camera = await ws.recv()


await get_cam()


async def test_get_cam():
    async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
        print(1)
        await ws.send(json.dumps({'key': key, 'force': True}))
        print(2)
        cam = await ws.recv()
        print(3)
        return json.loads(cam)

async def test_get_cam():
    async with websockets.connect('ws://51.178.46.24:9090/ws'):
        print(1)
    return True
