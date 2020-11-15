import asyncio
import time
import web_camera


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

