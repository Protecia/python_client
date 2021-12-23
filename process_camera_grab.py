import time
import cv2
import numpy as np
import httpx
from functools import partial


# retrieve latest frame
async def grab_rtsp(vcap, loop, logger, cam):
    ret, frame = await loop.run_in_executor(None, vcap.retrieve)
    logger.debug(f"resultat de la lecture rtsp : {ret}  pour {cam['name']}")
    if ret and len(frame) > 100:
        return frame
    else:
        return False


async def grab_http(cam, logger, loop):
    if cam['auth_type'] == 'B':
        auth = (cam['username'], cam['password'])
    else:  # cam['auth_type'] == 'D'
        auth = httpx.DigestAuth(cam['username'], cam['password'])
    # A client with a 10s timeout for connecting, and a 10s timeout elsewhere.
    timeout = httpx.Timeout(10.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            t = time.time()
            r = await client.get(cam['http'], auth=auth)
            logger.error(f'get http image {cam["http"]} in  {time.time() - t}s')
        if r.status_code == 200 and len(r.content) > 11000:
            logger.info(f'content of request is len  {len(r.content)}')
            array_np = await loop.run_in_executor(None, partial(np.asarray, bytearray(r.content), dtype="uint8"))
            frame = await loop.run_in_executor(None, partial(cv2.imdecode, array_np , 1))
            logger.info(f'frame with a len of {len(frame) if frame is not None else "None"}')
            if frame is None:
                logger.warning('bad camera download frame is None on {} \n'.format(cam['name']))
                return False
            else:
                return frame
        else:
            logger.warning('bad camera download on {} \n'.format(cam['name']))
            return False
    except httpx.HTTPError:
        logger.warning('network error on {} \n'.format(cam['name']))
        return False
